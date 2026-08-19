"""팀 공통 계약. 이 파일은 AI-1이 소유합니다.
변경 규칙: 필드 추가만 허용. 삭제·개명 금지. 신규 필드는 반드시 기본값 지정.
"""
from typing import Any, Literal, Optional
from datetime import date, datetime

from pydantic import BaseModel

# ──────────────────────────────────────────────────────────
# ui.type — 프론트 컴포넌트와 1:1
# ──────────────────────────────────────────────────────────
UiType = Literal[
    "none",             # 메시지만
    "profile_confirm",  # 추출 결과 확인
    "question",         # 슬롯 필링 질문
    "comparison",       # 은행 요건 비교
    "doc_preview",      # 서류 미리보기
    "approval",         # 승인 요청
]


class UiBlock(BaseModel):
    type: UiType = "none"
    payload: dict[str, Any] = {}


# ──────────────────────────────────────────────────────────
# 상태
# ──────────────────────────────────────────────────────────
TaskStatus = Literal["locked", "available", "in_progress", "done"]


class Task(BaseModel):
    id: str
    label: str
    status: TaskStatus
    prereq: list[str] = []
    blocked_by: list[str] = []      # 잠긴 이유(라벨)
    deadline: Optional[date] = None
    d_day: Optional[int] = None     # 백엔드가 계산해서 내려줌
    evidence: list[str] = []
    agency: str = ""                # 제출처 (예: 출입국·외국인청)
    required_docs: list[str] = []   # 지참 서류
    note: Optional[str] = None      # 조건 안내


class DocRef(BaseModel):
    id: str
    title: str
    action_id: str
    preview_url: str                # HTML — iframe용
    pdf_url: str
    created_at: datetime


class PendingApproval(BaseModel):
    action_id: str
    title: str


class SessionState(BaseModel):
    session_id: str
    locale: str = "ko"              # ko | en | vi
    profile: dict[str, Any] = {}
    tasks: list[Task] = []
    documents: list[DocRef] = []
    pending_approval: Optional[PendingApproval] = None


class AgentResponse(BaseModel):
    schema_version: str = "1"
    reply: str
    ui: UiBlock = UiBlock()
    state: SessionState


# ──────────────────────────────────────────────────────────
# ui.payload 5종 — FS-1은 이것만 보면 됨
# ──────────────────────────────────────────────────────────
class ProfileField(BaseModel):
    key: str
    label: str
    value: str
    confidence: float = 1.0         # < 0.9 면 확인 요청 하이라이트
    editable: bool = True


class ProfileConfirmPayload(BaseModel):
    doc_type: Literal["passport", "arc"]
    fields: list[ProfileField]


class Option(BaseModel):
    value: str
    label: str


class QuestionPayload(BaseModel):
    field: str
    label: str
    input_type: Literal["text", "select", "address"]
    options: list[Option] = []
    hint: Optional[str] = None


class ComparisonPayload(BaseModel):
    title: str
    columns: list[str]
    rows: list[dict[str, str]]
    note: str = "정보 제공 목적이며 특정 상품 추천이 아닙니다"
    as_of: str


class DocPreviewPayload(BaseModel):
    document_id: str
    title: str
    preview_url: str
    pdf_url: str
    warnings: list[str] = []


class ApprovalPayload(BaseModel):
    action_id: str
    title: str
    summary: list[str] = []
    document_id: Optional[str] = None
    evidence: list[str] = []
    risk_level: Literal["L1", "L2", "L3"] = "L2"


# ──────────────────────────────────────────────────────────
# 요청
# ──────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str
    message: str


class ExtractRequest(BaseModel):
    session_id: str
    file_key: str
    doc_type: Literal["passport", "arc"]


class ActionRequest(BaseModel):
    session_id: str


class ApproveRequest(BaseModel):
    session_id: str
    approved: bool = True


class PresignRequest(BaseModel):
    session_id: str
    filename: str
    content_type: str = "image/jpeg"


class PresignResponse(BaseModel):
    upload_url: str
    file_key: str


# ──────────────────────────────────────────────────────────
# 에러
# ──────────────────────────────────────────────────────────
class ErrorResponse(BaseModel):
    error: Literal[
        "extraction_failed",
        "validation_failed",
        "prerequisite_missing",
        "blocked_by_law",
        "internal",
    ]
    message: str
    details: dict[str, Any] = {}