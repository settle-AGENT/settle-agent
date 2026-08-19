"""Mock Agent API — 로직 없음, 응답 형태만 고정.

목적: 팀이 D1 아침부터 화면/라우팅을 붙일 수 있게 하는 것.
D2에 agent.invoke()로 교체되며, 응답 스키마는 그대로 유지됩니다.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.nodes.profiler import apply_edits, public_profile
from app.nodes.profiler import run as profiler_run
from app.api.schemas import (
    ActionRequest,
    AgentResponse,
    ApproveRequest,
    ChatRequest,
    ExtractRequest,
    PresignRequest,
    PresignResponse,
    SessionState,
    Task,
    UiBlock,
)

# repo_root/seed
SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
BASE_PROFILE: dict = json.loads((SEED_DIR / "profile.json").read_text(encoding="utf-8"))
BASE_TASKS: list[dict] = json.loads((SEED_DIR / "tasks.json").read_text(encoding="utf-8"))

app = FastAPI(
    title="Settle Agent API (Mock)",
    description="외국인 금융 정착 AI Agent — Mock 응답 서버",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock 전용 인메모리 세션 저장소 (실제로는 Checkpointer)
SESSIONS: dict[str, dict] = {}

DEFAULT_SID = "demo-001"


# ──────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────
def _new_session() -> dict:
    return {
        "profile": {},
        "tasks": copy.deepcopy(BASE_TASKS),
        "documents": [],
        "pending_approval": None,
        "slot_step": 0,
        "current_action": None,
    }


def _session(sid: str) -> dict:
    if sid not in SESSIONS:
        SESSIONS[sid] = _new_session()
    return SESSIONS[sid]


def _state(sid: str) -> SessionState:
    s = _session(sid)
    return SessionState(
        session_id=sid,
        locale="en",
        profile=public_profile(s["profile"]),   # 마스킹된 사본. 원본은 SESSIONS에
        tasks=[Task(**t) for t in s["tasks"]],
        documents=s["documents"],
        pending_approval=s["pending_approval"],
    )


def _unlock(sid: str, done_action: str) -> None:
    """done_action 완료 처리 후 prereq를 만족하게 된 액션 잠금 해제."""
    s = _session(sid)
    done = {t["id"] for t in s["tasks"] if t["status"] == "done"} | {done_action}
    for t in s["tasks"]:
        if t["id"] == done_action:
            t["status"] = "done"
        elif t["status"] == "locked" and all(p in done for p in t["prereq"]):
            t["status"] = "available"
            t["blocked_by"] = []


def _resp(sid: str, reply: str, ui_type: str = "none", payload: dict | None = None) -> AgentResponse:
    return AgentResponse(
        reply=reply,
        ui=UiBlock(type=ui_type, payload=payload or {}),
        state=_state(sid),
    )


# ──────────────────────────────────────────────────────────
# 슬롯 필링 질문 (Mock에서는 고정 3개)
# ──────────────────────────────────────────────────────────
QUESTIONS: list[dict] = [
    {
        "field": "org_name",
        "label": "Which school are you enrolled in?",
        "input_type": "text",
        "options": [],
        "hint": "As written on your enrollment certificate",
    },
    {
        "field": "addr_kr",
        "label": "What is your address in Korea?",
        "input_type": "address",
        "options": [
            {"value": "seoul-dongjak-369", "label": "서울특별시 동작구 상도로 369 (06978)"},
            {"value": "seoul-dongjak-371", "label": "서울특별시 동작구 상도로 371 (06978)"},
        ],
        "hint": "A building name is enough — we normalize it",
    },
    {
        "field": "purpose",
        "label": "What will you use this account for?",
        "input_type": "select",
        "options": [
            {"value": "living_expense", "label": "Living expenses"},
            {"value": "tuition", "label": "Tuition"},
            {"value": "salary", "label": "Salary"},
            {"value": "remittance", "label": "Remittance"},
        ],
    },
]

ACTION_TITLES = {
    "alien_registration": "Alien Registration — Integrated Application",
    "residence_change": "Change of Residence Report",
    "work_activity": "Activity Permit Application",
    "open_bank_account": "Bank Account Application",
}


# ──────────────────────────────────────────────────────────
# endpoints
# ──────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "mode": "mock"}


@app.post("/api/session", tags=["session"])
def create_session():
    SESSIONS[DEFAULT_SID] = _new_session()
    return {"session_id": DEFAULT_SID}


@app.post("/api/uploads/presign", response_model=PresignResponse, tags=["upload"])
def presign(req: PresignRequest):
    """실제로는 S3 presigned URL. Mock은 더미 URL."""
    return PresignResponse(
        upload_url="https://mock.local/upload",
        file_key=f"uploads/{req.session_id}/{req.filename}",
    )


@app.post("/api/profile/extract", response_model=AgentResponse, tags=["agent"])
def extract(req: ExtractRequest):
    s = _session(req.session_id)

    if req.doc_type == "passport":
        s["profile"] = {k: v for k, v in BASE_PROFILE.items() if v is not None}
        fields = [
            {"key": "name_en", "label": "Full name", "value": "NGUYEN VAN A",
             "confidence": 0.99, "editable": True},
            {"key": "nationality", "label": "Nationality", "value": "VIETNAM",
             "confidence": 0.99, "editable": True},
            {"key": "passport_no", "label": "Passport No.", "value": "M12345678",
             "confidence": 1.0, "editable": False},
            {"key": "birth_date", "label": "Date of birth", "value": "1999-01-01",
             "confidence": 0.97, "editable": True},
            {"key": "visa_type", "label": "Visa status", "value": "D-2",
             "confidence": 0.96, "editable": True},
            {"key": "stay_expiry", "label": "Stay expiry", "value": "2027-02-28",
             "confidence": 0.88, "editable": True},
        ]
        reply = (
            "Passport verified — MRZ checksum OK.\n"
            "You are on a D-2 student visa. Alien Registration comes first: "
            "87 days left before the legal deadline."
        )
    else:  # arc
        s["profile"].update({"arc_no_masked": "990101-*******", "visa_type": "D-2"})
        _unlock(req.session_id, "alien_registration")
        fields = [
            {"key": "arc_no", "label": "Registration No.", "value": "990101-*******",
             "confidence": 0.95, "editable": True},
            {"key": "visa_type", "label": "Visa status", "value": "D-2",
             "confidence": 0.98, "editable": True},
        ]
        reply = "Residence card verified. Bank account opening is now unlocked."

    return _resp(req.session_id, reply, "profile_confirm",
                 {"doc_type": req.doc_type, "fields": fields})


@app.post("/api/chat", response_model=AgentResponse, tags=["agent"])
def chat(req: ChatRequest):
    s = _session(req.session_id)
    msg = req.message.lower()

    # 1) 질문 의도 → 룰 판정 + 근거 인용 + 액션 제안
    if any(k in msg for k in ("work", "part-time", "part time", "job", "아르바이트")):
        return _resp(
            req.session_id,
            "Yes — D-2 holders may work part-time, but you must obtain an "
            "Activity Permit first, and that requires Alien Registration to be "
            "completed.\nSource: Immigration Act Art. 20",
        )

    # 2) 은행 비교
    if any(k in msg for k in ("bank", "account", "계좌")):
        return _resp(
            req.session_id,
            "Here are the requirements by bank for a D-2 visa.",
            "comparison",
            {
                "title": "Bank requirements for D-2",
                "columns": ["Bank", "Documents", "Non-face-to-face", "Languages"],
                "rows": [
                    {"Bank": "한빛은행", "Documents": "Passport, ARC, Enrollment cert",
                     "Non-face-to-face": "No", "Languages": "EN, VI"},
                    {"Bank": "다솜은행", "Documents": "Passport, ARC",
                     "Non-face-to-face": "Partial", "Languages": "EN"},
                    {"Bank": "미래로은행", "Documents": "Passport, ARC, Enrollment cert, Address proof",
                     "Non-face-to-face": "No", "Languages": "EN, VI, ZH"},
                ],
                "note": "정보 제공 목적이며 특정 상품 추천이 아닙니다",
                "as_of": "2026-08-18",
            },
        )

    # 3) 슬롯 필링 진행 중이면 다음 질문
    step = s["slot_step"]
    if s["current_action"] and step < len(QUESTIONS):
        s["slot_step"] += 1
        remaining = len(QUESTIONS) - s["slot_step"]
        if remaining:
            return _resp(req.session_id, "Got it.", "question", QUESTIONS[s["slot_step"]])
        return _resp(
            req.session_id,
            "All set. Generating your form...",
            "doc_preview",
            _build_doc(req.session_id, s["current_action"]),
        )

    return _resp(req.session_id, "Okay.")


def _build_doc(sid: str, action_id: str) -> dict:
    s = _session(sid)
    doc = {
        "id": "doc-001",
        "title": ACTION_TITLES.get(action_id, "Application Form"),
        "action_id": action_id,
        "preview_url": "/static/mock_document.html",
        "pdf_url": "/static/mock_document.pdf",
        "created_at": "2026-08-18T23:10:00+09:00",
    }
    s["documents"] = [doc]
    s["pending_approval"] = {"action_id": action_id, "title": "Book appointment + pre-submit"}
    return {
        "document_id": doc["id"],
        "title": doc["title"],
        "preview_url": doc["preview_url"],
        "pdf_url": doc["pdf_url"],
        "warnings": [],
    }


@app.post("/api/actions/{action_id}/start", response_model=AgentResponse, tags=["agent"])
def start_action(action_id: str, req: ActionRequest):
    s = _session(req.session_id)
    target = next((t for t in s["tasks"] if t["id"] == action_id), None)
    if target is None:
        raise HTTPException(404, "unknown action")
    if target["status"] == "locked":
        raise HTTPException(
            409,
            detail={"error": "prerequisite_missing",
                    "message": f"먼저 완료해야 합니다: {', '.join(target['blocked_by'])}",
                    "details": {"prereq": target["prereq"]}},
        )

    target["status"] = "in_progress"
    s["current_action"] = action_id
    s["slot_step"] = 0
    return _resp(
        req.session_id,
        "3 fields are missing. Let me ask.",
        "question",
        QUESTIONS[0],
    )


@app.post("/api/actions/{action_id}/preview", response_model=AgentResponse, tags=["agent"])
def preview_action(action_id: str, req: ActionRequest):
    return _resp(
        req.session_id,
        "Your form is ready. All 5 validation checks passed.",
        "doc_preview",
        _build_doc(req.session_id, action_id),
    )


@app.post("/api/actions/{action_id}/approve", response_model=AgentResponse, tags=["agent"])
def approve_action(action_id: str, req: ApproveRequest):
    s = _session(req.session_id)

    if not req.approved:
        s["pending_approval"] = None
        for t in s["tasks"]:
            if t["id"] == action_id and t["status"] == "in_progress":
                t["status"] = "available"
        return _resp(req.session_id, "Cancelled. Nothing was submitted.")

    s["pending_approval"] = None
    s["current_action"] = None
    _unlock(req.session_id, action_id)

    return _resp(
        req.session_id,
        "Appointment confirmed: Aug 25, 10:30 — Seoul Immigration Office.\n"
        "Checklist sent by email and added to your calendar.\n"
        "Receipt No. IMM-0908-14",
    )


@app.get("/api/ledger", tags=["agent"])
def ledger(session_id: str = DEFAULT_SID):
    return [
        {
            "action": "alien_registration",
            "risk_level": "L2",
            "approved_by": "user",
            "approved_at": "2026-08-18T23:12:00+09:00",
            "evidence": [
                {"law": "출입국관리법 제31조",
                 "url": "https://www.law.go.kr/법령/출입국관리법/제31조"}
            ],
            "result": {"receipt_no": "IMM-0908-14", "status": "received"},
        }
    ]


@app.post("/api/profile/extract-upload", response_model=AgentResponse, tags=["agent"])
async def extract_upload(
    session_id: str = Form(DEFAULT_SID),
    doc_type: str = Form(...),              # "arc_front" | "arc_back"
    file: UploadFile = File(...),
):
    """실제 OCR 경로. S3 없이 파일을 직접 받아 처리한다."""
    s = _session(session_id)
    image = await file.read()
    ext = (file.filename or "x.jpg").rsplit(".", 1)[-1].lower()

    try:
        state, payload = profiler_run(s, image, doc_type, ext=ext)
    except Exception as exc:
        raise HTTPException(422, detail={
            "error": "extraction_failed",
            "message": "신분증을 읽지 못했습니다. 밝은 곳에서 다시 촬영해주세요.",
            "details": {"reason": str(exc)},
        })

    low = [f["key"] for f in payload["fields"] if f["confidence"] < 0.90]
    reply = ("신분증을 확인했습니다. 값이 맞는지 봐주세요."
             if not low else
             f"신분증을 확인했습니다. {len(low)}개 항목은 확인이 필요합니다.")

    return _resp(session_id, reply, "profile_confirm", payload)


@app.post("/api/profile/confirm", response_model=AgentResponse, tags=["agent"])
def confirm_profile(req: ChatRequest):
    """확인 화면에서 사용자가 고친 값을 반영한다.

    req.message 에 JSON 문자열로 {"name_en": "...", ...} 를 담아 보낸다.
    (전용 요청 모델은 D2에 추가 — 지금은 스키마 변경 없이 처리)
    """
    s = _session(req.session_id)
    try:
        edits = json.loads(req.message) if req.message else {}
    except json.JSONDecodeError:
        raise HTTPException(422, detail={
            "error": "validation_failed",
            "message": "edits must be a JSON object",
            "details": {},
        })

    apply_edits(s, edits)
    return _resp(req.session_id, "확인해주셔서 감사합니다. 계속 진행할게요.")