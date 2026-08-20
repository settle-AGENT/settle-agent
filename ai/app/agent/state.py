"""AgentState — 그래프 전체가 공유하는 단일 상태.

설계 원칙
  - profile / tasks 두 개가 본체. 나머지는 진행 중 임시값이다.
  - 여기 담긴 값은 Checkpointer가 그대로 직렬화해 PostgreSQL에 저장한다.
    → 응답으로 나갈 값과 내부 값이 섞여 있으므로, 밖으로 내보낼 때는
      반드시 profiler.public_profile() 을 거친다.
  - 리스트/딕셔너리 필드는 reducer로 병합한다. 노드가 부분 갱신만 반환하면 된다.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

# ──────────────────────────────────────────────────────────
# reducers — 노드가 조각만 반환해도 병합된다
# ──────────────────────────────────────────────────────────
def merge_dict(old: dict | None, new: dict | None) -> dict:
    return {**(old or {}), **(new or {})}


def replace(old, new):
    """항상 교체한다.

    LangGraph는 노드가 키를 반환하지 않으면 reducer를 호출하지 않으므로
    "변경 없음"은 키 생략으로 표현된다. 따라서 여기서 None을 특별 취급하면
    필드를 비울 방법이 사라진다 (pending_approval=None 등).
    """
    return new


def union_list(old: list | None, new: list | None) -> list:
    """중복 없이 append (순서 유지)."""
    out = list(old or [])
    for x in (new or []):
        if x not in out:
            out.append(x)
    return out


# ──────────────────────────────────────────────────────────
# 하위 구조
# ──────────────────────────────────────────────────────────
RiskLevel = Literal["L1", "L2", "L3"]


class PendingAction(TypedDict, total=False):
    """승인 게이트에서 대기 중인 액션."""
    action_id: str
    title: str
    summary: list[str]
    document_id: Optional[str]
    evidence: list[str]
    risk_level: RiskLevel


class LedgerEntry(TypedDict, total=False):
    """에이전트가 실제로 수행한 행동 기록. 근거 법령을 함께 남긴다."""
    action: str
    tool: str
    risk_level: RiskLevel
    approved_by: Optional[str]
    approved_at: Optional[str]
    evidence: list[str]
    result: dict[str, Any]


# ──────────────────────────────────────────────────────────
# 메인 상태
# ──────────────────────────────────────────────────────────
class AgentState(TypedDict, total=False):
    # ── 식별 ──────────────────────────────────────────────
    session_id: str
    locale: str                                   # ko | en

    # ── 사용자 (본체 1) ───────────────────────────────────
    profile: Annotated[dict[str, Any], merge_dict]        # 평문 저장
    confidence: Annotated[dict[str, float], merge_dict]   # 필드별 OCR 신뢰도

    # ── 계획 (본체 2) ─────────────────────────────────────
    # tasks 는 매번 룰로 재계산하므로 병합하지 않고 통째로 교체한다.
    tasks: Annotated[list[dict], replace]
    completed: Annotated[list[str], union_list]           # 완료된 action_id
    in_progress: Annotated[list[str], replace]         # 진행 중인 action_id

    # ── 현재 진행 중인 액션 ───────────────────────────────
    current_action: Annotated[Optional[str], replace]
    missing_fields: Annotated[list[str], replace]         # 슬롯 필링 대상
    asked_field: Annotated[Optional[str], replace]        # 방금 물어본 필드
    ask: Annotated[Optional[str], replace]               # 이번 턴의 자유 질문
    last_qa: Annotated[Optional[str], replace]           # 마지막으로 답한 질문

    # ── 산출물 ────────────────────────────────────────────
    documents: Annotated[list[dict], union_list]
    pending_approval: Annotated[Optional[PendingAction], replace]
    # 사용자의 승인 응답. approval_gate 가 읽고 executor 로 보낼지 결정한다.
    approval_decision: Annotated[Optional[Literal["approve", "reject"]], replace]

    # ── 기록 ──────────────────────────────────────────────
    ledger: Annotated[list[LedgerEntry], operator.add]
    raw_texts: Annotated[list[str], replace]              # OCR 원문, 응답엔 미포함
    dropped: Annotated[list[str], replace]                # 검증 탈락 필드

    # ── 대화 ──────────────────────────────────────────────
    messages: Annotated[list[dict], operator.add]         # {role, content}

    # ── 이번 턴의 출력 (노드가 채우고 invoke가 꺼내 간다) ──
    reply: Annotated[Optional[str], replace]
    ui_type: Annotated[Optional[str], replace]
    ui_payload: Annotated[Optional[dict], replace]


# ──────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────
def new_state(session_id: str, locale: str = "en") -> AgentState:
    return AgentState(
        session_id=session_id,
        locale=locale,
        profile={},
        confidence={},
        tasks=[],
        completed=[],
        in_progress=[],
        current_action=None,
        missing_fields=[],
        asked_field=None,
        documents=[],
        pending_approval=None,
        approval_decision=None,
        ledger=[],
        raw_texts=[],
        dropped=[],
        messages=[],
        reply=None,
        ui_type="none",
        ui_payload={},
    )


def turn_output(state: AgentState) -> dict:
    """이번 턴에 노드들이 채운 출력만 뽑는다. invoke()가 응답으로 변환한다."""
    return {
        "reply": state.get("reply") or "",
        "ui": {
            "type": state.get("ui_type") or "none",
            "payload": state.get("ui_payload") or {},
        },
    }


def clear_turn(state: AgentState) -> dict:
    """다음 턴 시작 시 출력 필드를 비운다."""
    return {"reply": None, "ui_type": "none", "ui_payload": {}}
