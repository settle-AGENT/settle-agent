"""Settle Agent API

USE_MOCK=true  → 하드코딩 응답 (프론트 개발·데모 폴백용)
USE_MOCK=false → 실제 LangGraph 에이전트

응답 스키마는 두 모드가 동일하다. 프론트는 차이를 알 수 없다.
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv
import traceback

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.api.schemas import (  # noqa: E402
    ActionRequest,
    AgentResponse,
    ApproveRequest,
    ChatRequest,
    PresignRequest,
    PresignResponse,
)
from app.agent import service as agent
from app.extractors.arc import OcrFailed  # noqa: E402
from app.agent.service import PrerequisiteMissing  # noqa: E402

DEFAULT_SID = "demo-001"

app = FastAPI(
    title="Settle Agent API",
    description="국내 체류 외국인 금융 정착 AI Agent",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _warm_embedder() -> None:
    from app.tools import embed
    embed.warm()
    
@app.get("/health", tags=["meta"])
def health():
    return {
        "ok": True,
        "mode": "agent",
        "persistent": agent.is_persistent(),   # False 면 재시작 시 세션 소멸
    }


@app.post("/api/session", response_model=AgentResponse, tags=["session"])
def create_session(locale: str = "en", session_id: str | None = None):
    """session_id 를 주면 그 세션을 이어받고, 없으면 새로 만든다."""
    return agent.start_session(session_id, locale)


@app.post("/api/uploads/presign", response_model=PresignResponse, tags=["upload"])
def presign(req: PresignRequest):
    """실제 서비스는 S3 presigned URL. 지금은 직접 업로드를 쓴다."""
    return PresignResponse(
        upload_url="https://mock.local/upload",
        file_key=f"uploads/{req.session_id}/{req.filename}",
    )


@app.post("/api/profile/extract-upload", response_model=AgentResponse, tags=["agent"])
async def extract_upload(
    session_id: str = Form(DEFAULT_SID),
    doc_type: str = Form(...),              # arc_front | arc_back | passport
    file: UploadFile = File(...),
):
    image = await file.read()
    raw_ext = (file.filename or "x.jpg").rsplit(".", 1)[-1].lower()
    ext = {"jpeg": "jpg", "jpe": "jpg", "heic": "jpg", "heif": "jpg"}.get(raw_ext, raw_ext)
    if ext not in ("jpg", "png", "pdf", "tiff"):
        ext = "jpg"
    try:
        return agent.extract(session_id, image, doc_type, ext=ext)

    except OcrFailed as exc:
        # 예상된 실패 — 사용자가 다시 촬영하면 해결된다. 422 로 안내한다.
        raise HTTPException(422, detail=agent.localize_error(session_id, {
            "error": "extraction_failed",
            "message": str(exc),
            "details": {"doc_type": doc_type, "filename": file.filename, "ext": ext},
        }))

    except Exception as exc:                                  # noqa: BLE001
        # 버그 — 사용자에게 "다시 촬영하세요" 라고 하면 영원히 해결되지 않는다.
        traceback.print_exc()
        raise HTTPException(500, detail=agent.localize_error(session_id, {
            "error": "internal",
            "message": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            "details": {"reason": f"{type(exc).__name__}: {exc}",
                        "doc_type": doc_type, "filename": file.filename},
        }))


@app.post("/api/profile/confirm", response_model=AgentResponse, tags=["agent"])
def confirm_profile(req: ChatRequest):
    """확인 화면에서 고친 값 반영. message 에 JSON 문자열을 담는다."""
    try:
        edits = json.loads(req.message) if req.message else {}
    except json.JSONDecodeError:
        raise HTTPException(422, detail=agent.localize_error(req.session_id, {
            "error": "validation_failed",
            "message": "수정한 값을 읽지 못했습니다. 다시 시도해주세요.",
            "details": {},
        }))
    return agent.apply_profile_edits(req.session_id, edits)


@app.post("/api/chat", response_model=AgentResponse, tags=["agent"])
def chat(req: ChatRequest):
    return agent.send_message(req.session_id, req.message)


@app.post("/api/actions/{action_id}/start", response_model=AgentResponse, tags=["agent"])
def start_action(action_id: str, req: ActionRequest):
    try:
        return agent.start_action(req.session_id, action_id)
    except PrerequisiteMissing as exc:
        raise HTTPException(409, detail=agent.localize_error(req.session_id,
                                                            exc.detail()))


@app.post("/api/actions/{action_id}/approve", response_model=AgentResponse, tags=["agent"])
def approve_action(action_id: str, req: ApproveRequest):
    return agent.approve(req.session_id, action_id, req.approved)


@app.get("/api/state", response_model=AgentResponse, tags=["agent"])
def read_state(session_id: str = DEFAULT_SID):
    """새로고침 후 화면 복원용."""
    return agent.get_state(session_id)


@app.get("/api/ledger", tags=["agent"])
def ledger(session_id: str = DEFAULT_SID):
    return agent.get_ledger(session_id)


# ── 생성된 서류 서빙 ─────────────────────────────────────
from pathlib import Path as _Path  # noqa: E402

OUTPUT_DIR = _Path(__file__).resolve().parents[1] / "output"


def _session_of(document_id: str) -> str:
    """서류 id 는 doc_builder 가 "{session_id}-{action_id}" 로 만든다.

    URL 에 session_id 를 따로 실어 보내지 않고 여기서 되찾는다.
    action_id 에는 하이픈이 없으므로 마지막 하이픈이 경계다.
    """
    return document_id.rsplit("-", 1)[0]


@app.get("/api/documents/{document_id}/preview", response_class=HTMLResponse,
         tags=["documents"])
def document_preview(document_id: str):
    """iframe 으로 띄울 HTML. PDF 뷰어 없이 미리보기가 된다."""
    path = OUTPUT_DIR / f"{document_id}.html"
    if not path.exists():
        # 이 두 엔드포인트만 detail 이 문자열이다. 형태는 그대로 두고 언어만 맞춘다.
        raise HTTPException(404, agent.localize_message(
            _session_of(document_id), "요청하신 서류를 찾을 수 없습니다."))
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/api/documents/{document_id}.pdf", tags=["documents"])
def document_pdf(document_id: str):
    path = OUTPUT_DIR / f"{document_id}.pdf"
    if not path.exists():
        # 이 두 엔드포인트만 detail 이 문자열이다. 형태는 그대로 두고 언어만 맞춘다.
        raise HTTPException(404, agent.localize_message(
            _session_of(document_id), "요청하신 서류를 찾을 수 없습니다."))
    return FileResponse(path, media_type="application/pdf",
                        filename=f"{document_id}.pdf")