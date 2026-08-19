"""Agent Graph — 통제된 상태 기계.

설계 원칙
  - LLM에게 자율적인 툴 선택권을 주지 않는다. 경로는 이 파일에 고정되어 있다.
  - 승인 게이트를 우회하는 엣지가 존재하지 않는다. 그래서 L2 액션은
    LLM이 어떻게 동작하든 사용자 승인 없이 실행될 수 없다.
  - LLM은 Router(의도 분류)와 Explainer(설명 생성)에서만 쓰인다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from langgraph.graph import END, StateGraph

from app.agent.state import AgentState, clear_turn, new_state
from app.nodes.planner import build_task_graph, summary
from app.nodes.doc_builder import DocumentIncomplete, render
from app.nodes.profiler import profile_to_payload
from app.rules.loader import actions_for, evidence_labels
from app.tools import llm

KST = timezone.utc  # 표시용. 실제 타임존은 서비스 설정에서 주입한다.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────
# 슬롯 필링 질문 정의 (mappings 완성 전까지 여기서 관리)
# ──────────────────────────────────────────────────────────
QUESTIONS: dict[str, dict] = {
    "entry_date": {
        "label": "When did you enter Korea?",
        "input_type": "text",
        "options": [],
        "hint": "YYYY-MM-DD — 여권 입국심사인에 찍혀 있습니다",
    },
    "org_name": {
        "label": "Which school are you enrolled in?",
        "input_type": "text",
        "options": [],
        "hint": "As written on your enrollment certificate",
    },
    "phone_kr": {
        "label": "What is your phone number in Korea?",
        "input_type": "text",
        "options": [],
    },
    "purpose": {
        "label": "What will you use this account for?",
        "input_type": "select",
        "options": [
            {"value": "living_expense", "label": "Living expenses"},
            {"value": "tuition", "label": "Tuition"},
            {"value": "salary", "label": "Salary"},
            {"value": "remittance", "label": "Remittance"},
        ],
    },
    "income_source": {
        "label": "Where does your money come from?",
        "input_type": "select",
        "options": [
            {"value": "scholarship", "label": "Scholarship"},
            {"value": "family_support", "label": "Family support"},
            {"value": "part_time", "label": "Part-time job"},
            {"value": "savings", "label": "Savings"},
        ],
    },
}

# 액션별 필수 필드 (D2에 mappings/*.yaml 로 이관)
ACTION_FIELDS: dict[str, list[str]] = {
    "alien_registration": ["entry_date", "org_name", "phone_kr"],
    "residence_change": ["phone_kr"],
    "work_activity": ["org_name"],
    "open_bank_account": ["org_name", "phone_kr", "purpose", "income_source"],
}

ACTION_TITLES: dict[str, str] = {
    "alien_registration": "출입국 방문예약 + 사전접수",
    "residence_change": "체류지 변경신고 접수",
    "work_activity": "체류자격외활동허가 신청",
    "open_bank_account": "은행 지점 예약 + 사전접수",
}


# ══════════════════════════════════════════════════════════
# 노드
# ══════════════════════════════════════════════════════════
def planner(state: AgentState) -> dict:
    """룰 엔진으로 Task Graph를 계산한다. LLM 없음."""
    profile = state.get("profile", {})
    if not profile.get("visa_type"):
        return {"tasks": []}

    tasks = build_task_graph(
        profile,
        completed=set(state.get("completed", [])),
        in_progress=set(state.get("in_progress", [])),
    )
    return {"tasks": tasks}


def router(state: AgentState) -> dict:
    """다음에 무엇을 할지 결정한다. 분기 자체는 코드가 소유한다."""
    return {}


def route_from_router(state: AgentState) -> Literal[
    "slot_filler", "doc_builder", "approval_gate", "explainer"
]:
    if state.get("pending_approval"):
        return "approval_gate"

    action = state.get("current_action")
    if not action:
        return "explainer"

    missing = _missing_fields(state, action)
    return "slot_filler" if missing else "doc_builder"


def _missing_fields(state: AgentState, action: str) -> list[str]:
    """현재 액션에 필요한 필드 중 프로필에 없는 것.

    다른 액션의 기한 필드(예: residence_change 의 move_date)를 끌어오지 않는다.
    """
    profile = state.get("profile", {})
    need = list(ACTION_FIELDS.get(action, []))

    # 이 액션 자신의 기한 기준일만 추가한다 (예: alien_registration → entry_date)
    spec = actions_for(profile.get("visa_type")).get(action, {})
    rule = spec.get("deadline")
    if rule and rule.get("from") and rule["from"] not in need:
        need.insert(0, rule["from"])

    return [f for f in need if not profile.get(f)]


def slot_filler(state: AgentState) -> dict:
    """부족한 필드 중 하나를 묻는다.

    무엇을 물을지는 코드가 정한다 (_missing_fields).
    LLM 은 그 필드에 대한 **문장만** 만든다. 실패하면 고정 문구로 폴백.
    """
    action = state.get("current_action")
    missing = _missing_fields(state, action)
    if not missing:
        return {"missing_fields": []}

    field = missing[0]
    q = QUESTIONS.get(field, {"label": field, "input_type": "text", "options": []})
    locale = state.get("locale", "en")

    label, hint = q["label"], q.get("hint")
    lead = f"{len(missing)}개만 더 여쭤볼게요." if len(missing) > 1 else "마지막 질문입니다."

    # LLM 은 문장 생성만. 실패해도 흐름이 끊기지 않는다.
    if llm.available():
        written = llm.ask_field(
            field,
            label=q["label"],
            locale=locale,
            context=state.get("profile", {}),
            remaining=len(missing),
        )
        if written and written.get("question"):
            label = written["question"]
            hint = written.get("hint") or hint
            lead = label          # 채팅 버블이 비지 않도록 질문을 그대로 넣는다

    return {
        "missing_fields": missing,
        "asked_field": field,
        "reply": lead,
        "ui_type": "question",
        "ui_payload": {
            "field": field,
            "label": label,
            "input_type": q["input_type"],
            "options": q.get("options", []),
            "hint": hint,
        },
    }


def doc_builder(state: AgentState) -> dict:
    """서류를 실제로 생성하고 승인 대기 상태로 만든다."""
    action = state["current_action"]
    profile = state.get("profile", {})
    spec = actions_for(profile.get("visa_type")).get(action, {})

    form = spec.get("form")
    if not form:
        return {
            "reply": "이 단계는 서류 없이 진행됩니다.",
            "ui_type": "none",
            "ui_payload": {},
        }

    try:
        result = render(
            form,
            profile,
            confidence=state.get("confidence", {}),
            variant=spec.get("form_type", "default"),
            required_docs=spec.get("required_docs", []),
            account_type=spec.get("account_type", "limited"),
            doc_id=f"{state['session_id']}-{action}",
        )
    except DocumentIncomplete as exc:
        return {
            "missing_fields": exc.missing,
            "reply": "서류 작성에 필요한 정보가 아직 부족합니다.",
            "ui_type": "none",
            "ui_payload": {},
        }

    doc = {
        "id": result["document_id"],
        "title": result["title"],
        "action_id": action,
        "preview_url": f"/api/documents/{result['document_id']}/preview",
        "pdf_url": f"/api/documents/{result['document_id']}.pdf",
        "created_at": _now(),
    }

    warnings = [f"{k} 값을 한 번 확인해주세요" for k in result["low_confidence"]]

    pending = {
        "action_id": action,
        "title": ACTION_TITLES.get(action, action),
        "summary": [ACTION_TITLES.get(action, action), "준비물 체크리스트 발송"],
        "document_id": doc["id"],
        "evidence": evidence_labels(spec.get("evidence", [])),
        "risk_level": spec.get("risk_level", "L2"),
    }

    checks = "검증 5개 항목 모두 통과했습니다." if not warnings else \
             f"검증 통과. {len(warnings)}개 항목은 확인을 권합니다."

    return {
        "documents": [doc],
        "pending_approval": pending,
        "reply": f"서류를 작성했습니다. {checks}",
        "ui_type": "doc_preview",
        "ui_payload": {
            "document_id": doc["id"],
            "title": doc["title"],
            "preview_url": doc["preview_url"],
            "pdf_url": doc["pdf_url"],
            "warnings": warnings,
        },
    }


def approval_gate(state: AgentState) -> dict:
    """risk_level 과 사용자 응답에 따라 실행 여부를 가른다.

    L1  자동 통과
    L2  사용자 승인 필요 → 승인 UI 를 띄우고 턴 종료. 다음 턴에
        approval_decision 이 들어오면 executor 로 넘어간다.
    L3  법적으로 대행 불가 → 실행하지 않고 안내만
    """
    pending = state.get("pending_approval") or {}
    risk = pending.get("risk_level", "L2")
    decision = state.get("approval_decision")

    if risk == "L3":
        return {
            "pending_approval": None,
            "approval_decision": None,
            "reply": ("이 단계는 본인만 수행할 수 있습니다. "
                      "준비는 끝났으니 창구에서 본인확인만 진행하시면 됩니다."),
            "ui_type": "none",
            "ui_payload": {},
        }

    if decision == "reject":
        action = pending.get("action_id")
        return {
            "pending_approval": None,
            "approval_decision": None,
            "current_action": None,
            "in_progress": [a for a in state.get("in_progress", []) if a != action],
            "reply": "취소했습니다. 아무것도 제출되지 않았습니다.",
            "ui_type": "none",
            "ui_payload": {},
        }

    if decision == "approve" or risk == "L1":
        return {}                       # executor 로 진행

    return {
        "reply": "아래 내용을 실행할까요?",
        "ui_type": "approval",
        "ui_payload": dict(pending),
    }


def route_from_gate(state: AgentState) -> Literal["executor", "__end__"]:
    pending = state.get("pending_approval") or {}
    if not pending:
        return END                      # L3 / 거절 / 대기 중 아님
    if pending.get("risk_level") == "L1":
        return "executor"
    if state.get("approval_decision") == "approve":
        return "executor"
    return END                          # L2 — 사용자 응답 대기


def executor(state: AgentState) -> dict:
    """승인된 액션을 실행하고 Ledger에 남긴다."""
    pending = state.get("pending_approval") or {}
    action = pending.get("action_id") or state.get("current_action")

    # 실제 기관 호출은 Mock Institution API. 여기서는 결과만 기록한다.
    result = {"receipt_no": f"RCPT-{action[:6].upper()}-0001", "status": "received"}

    entry = {
        "action": action,
        "tool": "submit_application",
        "risk_level": pending.get("risk_level", "L2"),
        "approved_by": "user",
        "approved_at": _now(),
        "evidence": pending.get("evidence", []),
        "result": result,
    }

    return {
        "completed": [action],
        "in_progress": [],
        "pending_approval": None,
        "approval_decision": None,
        "current_action": None,
        "ledger": [entry],
        "reply": (f"접수되었습니다. 접수번호 {result['receipt_no']}\n"
                  "준비물 체크리스트를 이메일로 보냈습니다."),
        "ui_type": "none",
        "ui_payload": {},
    }


def explainer(state: AgentState) -> dict:
    """상황 안내. 판정은 룰이 끝냈고, LLM 은 말로 옮기기만 한다."""
    tasks = state.get("tasks") or []
    locale = state.get("locale", "en")

    if not tasks:
        base = "신분증을 올려주시면 무엇을 하셔야 하는지 알려드릴게요."
        return {"reply": llm.translate(base, locale) if llm.available() else base,
                "ui_type": "none"}

    base = summary(tasks)

    if llm.available():
        nxt = next((t for t in tasks if t["status"] == "available"), None)
        spoken = llm.explain({
            "available_count": sum(1 for t in tasks if t["status"] == "available"),
            "next_action_label": nxt["label"] if nxt else None,
            "d_day": nxt["d_day"] if nxt else None,
            "blocked": [{"label": t["label"], "blocked_by": t["blocked_by"]}
                        for t in tasks if t["status"] == "locked"][:3],
            "evidence": nxt["evidence"] if nxt else [],
        }, locale=locale)
        if spoken:
            return {"reply": spoken, "ui_type": "none"}

    return {"reply": base, "ui_type": "none"}


def ledger_writer(state: AgentState) -> dict:
    """Executor 이후 Task Graph를 다시 계산한다 (잠금 해제 반영)."""
    return planner(state)


# ══════════════════════════════════════════════════════════
# 그래프 조립
# ══════════════════════════════════════════════════════════
def build_graph(checkpointer=None):
    g = StateGraph(AgentState)

    g.add_node("planner", planner)
    g.add_node("router", router)
    g.add_node("slot_filler", slot_filler)
    g.add_node("doc_builder", doc_builder)
    g.add_node("approval_gate", approval_gate)
    g.add_node("executor", executor)
    g.add_node("explainer", explainer)
    g.add_node("replanner", ledger_writer)

    g.set_entry_point("planner")
    g.add_edge("planner", "router")

    g.add_conditional_edges("router", route_from_router, {
        "slot_filler": "slot_filler",
        "doc_builder": "doc_builder",
        "approval_gate": "approval_gate",
        "explainer": "explainer",
    })

    g.add_edge("slot_filler", END)
    g.add_edge("doc_builder", "approval_gate")

    g.add_conditional_edges("approval_gate", route_from_gate, {
        "executor": "executor",
        END: END,
    })

    g.add_edge("executor", "replanner")
    g.add_edge("replanner", END)
    g.add_edge("explainer", END)

    return g.compile(checkpointer=checkpointer)


# 승인 게이트를 우회하는 엣지가 없음을 코드로 보증한다.
# executor 로 들어오는 유일한 경로는 approval_gate 이다.
GATED_ENTRY = {"executor": ["approval_gate"]}