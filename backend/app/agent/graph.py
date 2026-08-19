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
    "birth_date": {
        "label": "What is your date of birth?",
        "input_type": "text",
        "options": [],
        "hint": "YYYY-MM-DD",
    },
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
    "alien_registration": ["birth_date", "entry_date", "org_name", "phone_kr"],
    "residence_change": ["birth_date", "phone_kr"],
    "work_activity": ["org_name"],
    "open_bank_account": ["birth_date", "org_name", "phone_kr",
                          "purpose", "income_source"],
}

ACTION_TITLES: dict[str, str] = {
    "alien_registration": "외국인등록 신청서 제출",
    "residence_change": "체류지 변경신고 제출",
    "work_activity": "체류자격외활동허가 신청서 제출",
    "open_bank_account": "계좌개설 신청서 제출",
}

AGENCY_LABEL: dict[str, str] = {
    "immigration": "출입국·외국인청",
    "bank": "은행 영업점",
    "telecom": "통신사 대리점",
    "immigration_or_community_center": "출입국·외국인청 또는 주민센터",
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
        labels = {
            "name_en": "영문 성명", "birth_date": "생년월일", "gender": "성별",
            "nationality": "국적", "passport_no": "여권번호", "arc_no": "외국인등록번호",
            "addr_kr": "국내 주소", "phone_kr": "국내 연락처", "org_name": "소속 기관",
        }
        need = ", ".join(labels.get(k, k) for k in exc.missing)
        return {
            "missing_fields": exc.missing,
            "reply": f"서류를 작성하려면 {need}이(가) 더 필요합니다.",
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

    from app.nodes.doc_builder import DOC_LABELS
    docs = [DOC_LABELS.get(d, d) for d in spec.get("required_docs", [])]
    agency = AGENCY_LABEL.get(spec.get("agency", ""), spec.get("agency", ""))

    summary_lines = [f"{ACTION_TITLES.get(action, action)}"]
    if agency:
        summary_lines.append(f"제출처 · {agency}")
    if docs:
        summary_lines.append("지참 서류 · " + ", ".join(docs))

    pending = {
        "action_id": action,
        "title": ACTION_TITLES.get(action, action),
        "summary": summary_lines,
        "document_id": doc["id"],
        "preview_url": doc["preview_url"],      # 승인 화면에서 서류를 바로 본다
        "pdf_url": doc["pdf_url"],
        "warnings": warnings,
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
def route_from_doc(state: AgentState) -> Literal["approval_gate", "__end__"]:
    """서류가 실제로 만들어졌을 때만 승인 단계로 넘어간다."""
    return "approval_gate" if state.get("pending_approval") else END

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

    # 실제 기관 접수는 제휴 시 기관 API 호출로 대체된다.
    # 지금은 아무것도 제출하지 않는다 — 접수번호를 만들어내지 않는 이유다.
    spec = actions_for(state.get("profile", {}).get("visa_type")).get(action, {})
    agency = AGENCY_LABEL.get(spec.get("agency", ""), "담당 기관")

    doc = next((d for d in reversed(state.get("documents", []))
                if d.get("action_id") == action), None)
    task = next((t for t in state.get("tasks", []) if t["id"] == action), None)

    result = {
        "document_id": doc["id"] if doc else None,
        "status": "prepared",              # submitted 아님
    }

    entry = {
        "action": action,
        "tool": "prepare_application",
        "risk_level": pending.get("risk_level", "L2"),
        "approved_by": "user",
        "approved_at": _now(),
        "evidence": pending.get("evidence", []),
        "result": result,
    }

    lines = [f"{ACTION_TITLES.get(action, action)} 작성이 끝났습니다.",
             f"{agency}에 방문해 본인확인 후 제출하시면 됩니다."]
    if task:
        if task.get("required_docs"):
            lines.append("지참 서류 · " + ", ".join(task["required_docs"]))
        if task.get("deadline"):
            d = task.get("d_day")
            if d is not None and d < 0:
                lines.append(f"기한 · {task['deadline']} — 이미 {abs(d)}일 "
                             f"지났습니다. 지연 사유 확인이 필요합니다.")
            elif d is not None:
                lines.append(f"기한 · {task['deadline']} (D-{d})")
            else:
                lines.append(f"기한 · {task['deadline']}")

    return {
        "completed": [action],
        "in_progress": [],
        "pending_approval": None,
        "approval_decision": None,
        "current_action": None,
        "ledger": [entry],
        "reply": "\n".join(lines),
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
            "next_action_agency": nxt.get("agency") if nxt else None,
            "next_action_documents": nxt.get("required_docs") if nxt else [],
            "d_day": nxt["d_day"] if nxt else None,
            "blocked": [{"label": t["label"], "blocked_by": t["blocked_by"]}
                        for t in tasks if t["status"] == "locked"][:3],
            "evidence": nxt["evidence"] if nxt else [],
            "call_to_action": (f"Tell the user to tap the \"{nxt['label']}\" card to start."
                               if nxt else None),
        }, locale=locale)
        if spoken:
            return {"reply": spoken, "ui_type": "none"}

    return {"reply": base, "ui_type": "none"}

# 사용자의 목표를 우선한다. 조건부 액션(체류지 변경 등)은 스스로 권하지 않는다.
NEXT_PRIORITY = ["open_bank_account", "alien_registration", "mobile_subscription"]
def ledger_writer(state: AgentState) -> dict:
    """Executor 이후 Task Graph를 다시 계산하고, 새로 열린 일을 알린다."""
    out = planner(state)
    tasks = out.get("tasks") or []

    avail = [t for t in tasks if t["status"] == "available"]
    nxt = next((t for a in NEXT_PRIORITY for t in avail if t["id"] == a), None)
    if not nxt:
        return out

    line = f"이제 '{nxt['label']}'을(를) 하실 수 있습니다."
    if nxt.get("agency"):
        line += f" 제출처는 {nxt['agency']}입니다."

    out["reply"] = (state.get("reply") or "") + "\n\n" + line
    out["ui_type"] = "none"
    return out


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
    g.add_conditional_edges("doc_builder", route_from_doc, {
        "approval_gate": "approval_gate",
        END: END,
    })

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
