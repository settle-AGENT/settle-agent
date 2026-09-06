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
import queue
import threading

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
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
from app.agent.service import (  # noqa: E402
    ApprovalMismatch,
    IdentityMismatch,
    NothingToApprove,
    PrerequisiteMissing,
)

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
    from app.tools import embed, rag_store
    embed.warm()
    # 벡터가 비어 있으면 검색이 BM25 단독으로 조용히 떨어진다. 기동할 때
    # 채우고, 진행 상태를 /health 로 드러낸다. 적재는 기동을 막지 않는다.
    rag_store.ensure_loaded_async()


@app.get("/health", tags=["meta"])
def health():
    from app.tools import rag_store
    from app.rules import loader
    return {
        "ok": True,
        "mode": "agent",
        "persistent": agent.is_persistent(),   # False 면 재시작 시 세션 소멸
        "rag": rag_store.status(),             # ready 가 False 면 BM25 단독
        # 이 컨테이너가 어느 판을 근거로 답하는지. 배포된 것이 낡았는지
        # 밖에서 확인하려면 이 값이 필요하다.
        "sources": {
            "manifest": loader.SOURCES_VERSION,
            "matrix": loader.MATRIX_VERSION,
            "items": loader.source_versions(),
        },
    }


@app.post("/api/session", response_model=AgentResponse, tags=["session"])
def create_session(locale: str = "en", session_id: str | None = None,
                   reset: bool = False, source_session_id: str | None = None):
    """session_id 를 주면 그 세션을 이어받고, 없으면 새로 만든다."""
    if reset and session_id:
        return agent.reset_session(session_id, locale)
    return agent.start_session(session_id, locale, source_session_id)


@app.post("/api/uploads/presign", response_model=PresignResponse, tags=["upload"])
def presign(req: PresignRequest):
    """실제 서비스는 S3 presigned URL. 지금은 직접 업로드를 쓴다."""
    return PresignResponse(
        upload_url="https://mock.local/upload",
        file_key=f"uploads/{req.session_id}/{req.filename}",
    )


@app.post("/api/profile/extract-upload", response_model=AgentResponse, tags=["agent"])
async def extract_upload(
    session_id: str = Form(...),
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

    except IdentityMismatch as exc:
        # 다른 사람의 서류다. 재촬영이 아니라 서류를 다시 고르게 해야 한다.
        raise HTTPException(422, detail=agent.localize_error(session_id,
                                                             exc.detail()))

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
        # 예외 메시지를 응답에 싣지 않는다. 여기까지 오는 예외는 OCR·프로필
        # 처리 중에 난 것이라, 메시지에 신분증에서 읽은 값이나 프로필이 섞여
        # 있을 수 있다. 그것이 클라이언트로 나가면 마스킹도 암호화도 소용없다.
        # 원인은 위 traceback 으로 서버 로그에만 남긴다. 타입은 개인정보를
        # 담지 않으면서 어디서 깨졌는지 좁혀 주므로 남긴다.
        raise HTTPException(500, detail=agent.localize_error(session_id, {
            "error": "internal",
            "message": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            "details": {"reason": type(exc).__name__, "doc_type": doc_type},
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


# 이 경로는 응답 조립(_localized)을 거치지 않으므로 여기서 locale 을 고른다.
STREAM_ERROR = {
    "ko": "답변을 만들지 못했습니다. 잠시 후 다시 시도해주세요.",
    "en": "I could not put together an answer. Please try again in a moment.",
}


@app.post("/api/chat/stream", tags=["agent"])
def chat_stream(req: ChatRequest):
    """Stream actual agent execution stages, followed by the final AgentResponse."""
    events: queue.Queue = queue.Queue()

    def emit(step: str, label: str) -> None:
        events.put({"type": "progress", "step": step, "label": label})

    def run() -> None:
        try:
            excerpt = " ".join(req.message.strip().split())[:24]
            events.put({"type": "progress", "step": "start", "label": f"‘{excerpt}’ 질문을 받았어요"})
            result = agent.send_message(req.session_id, req.message, emit=emit)
            events.put({"type": "result", "data": result})
        except Exception as exc:  # noqa: BLE001
            # extract-upload 와 같은 이유로 예외 메시지를 내보내지 않는다.
            # 이 경로는 프로필·대화를 들고 도는 그래프 전체를 감싸고 있어서,
            # 어떤 값이 예외 문자열에 섞일지 여기서 알 수 없다.
            traceback.print_exc()
            locale = agent.locale_of(req.session_id)
            events.put({"type": "error",
                        "message": STREAM_ERROR.get(locale, STREAM_ERROR["en"]),
                        "reason": type(exc).__name__})
        finally:
            from app.tools import progress as progress_events
            progress_events.set_emitter(req.session_id, None)
            events.put(None)

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            event = events.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/actions/{action_id}/start", response_model=AgentResponse, tags=["agent"])
def start_action(action_id: str, req: ActionRequest):
    try:
        return agent.start_action(req.session_id, action_id)
    except PrerequisiteMissing as exc:
        raise HTTPException(409, detail=agent.localize_error(req.session_id,
                                                            exc.detail()))


@app.post("/api/actions/{action_id}/preview", response_model=AgentResponse, tags=["agent"])
def preview_action(action_id: str, req: ActionRequest):
    """서류를 만들고 승인 대기 상태로 만든다.

    백엔드는 ui.type == "doc_preview" 일 때만 pdf_url 을 내려받아 저장한다.
    부족한 값이 남아 있으면 ui.type 은 "question" 이고 서류는 만들어지지 않는다.
    """
    try:
        return agent.preview_action(req.session_id, action_id)
    except PrerequisiteMissing as exc:
        raise HTTPException(409, detail=agent.localize_error(req.session_id,
                                                             exc.detail()))


@app.post("/api/actions/{action_id}/approve", response_model=AgentResponse, tags=["agent"])
def approve_action(action_id: str, req: ApproveRequest):
    try:
        return agent.approve(req.session_id, action_id, req.approved)
    except (NothingToApprove, ApprovalMismatch) as exc:
        # 409 — 클라이언트가 다시 상태를 읽고 재시도하면 해결된다.
        raise HTTPException(409, detail=agent.localize_error(req.session_id,
                                                             exc.detail()))


@app.get("/api/state", response_model=AgentResponse, tags=["agent"])
def read_state(session_id: str):
    """새로고침 후 화면 복원용."""
    return agent.get_state(session_id)


@app.get("/api/ledger", tags=["agent"])
def ledger(session_id: str):
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
