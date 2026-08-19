"""Settle Agent API

USE_MOCK=true  → 하드코딩 응답 (프론트 개발·데모 폴백용)
USE_MOCK=false → 실제 LangGraph 에이전트

응답 스키마는 두 모드가 동일하다. 프론트는 차이를 알 수 없다.
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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
from app.agent import service as agent  # noqa: E402
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


@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "mode": "agent"}


@app.post("/api/session", response_model=AgentResponse, tags=["session"])
def create_session(locale: str = "en"):
    return agent.start_session(DEFAULT_SID, locale)


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
    ext = (file.filename or "x.jpg").rsplit(".", 1)[-1].lower()
    try:
        return agent.extract(session_id, image, doc_type, ext=ext)
    except Exception as exc:                                  # noqa: BLE001
        raise HTTPException(422, detail={
            "error": "extraction_failed",
            "message": "신분증을 읽지 못했습니다. 밝은 곳에서 다시 촬영해주세요.",
            "details": {"reason": str(exc)},
        })


@app.post("/api/profile/confirm", response_model=AgentResponse, tags=["agent"])
def confirm_profile(req: ChatRequest):
    """확인 화면에서 고친 값 반영. message 에 JSON 문자열을 담는다."""
    try:
        edits = json.loads(req.message) if req.message else {}
    except json.JSONDecodeError:
        raise HTTPException(422, detail={
            "error": "validation_failed",
            "message": "edits must be a JSON object",
            "details": {},
        })
    return agent.apply_profile_edits(req.session_id, edits)


@app.post("/api/chat", response_model=AgentResponse, tags=["agent"])
def chat(req: ChatRequest):
    return agent.send_message(req.session_id, req.message)


@app.post("/api/actions/{action_id}/start", response_model=AgentResponse, tags=["agent"])
def start_action(action_id: str, req: ActionRequest):
    try:
        return agent.start_action(req.session_id, action_id)
    except PrerequisiteMissing as exc:
        raise HTTPException(409, detail=exc.detail())


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