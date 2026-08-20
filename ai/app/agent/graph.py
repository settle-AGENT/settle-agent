"""Agent Graph — 통제된 상태 기계.

설계 원칙
  - LLM에게 자율적인 툴 선택권을 주지 않는다. 경로는 이 파일에 고정되어 있다.
  - 승인 게이트를 우회하는 엣지가 존재하지 않는다. 그래서 L2 액션은
    LLM이 어떻게 동작하든 사용자 승인 없이 실행될 수 없다.
  - LLM은 Router(의도 분류)와 Explainer(설명 생성)에서만 쓰인다.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Literal

from langgraph.graph import END, StateGraph

from app.agent.state import AgentState, clear_turn, new_state
from app.nodes import qa, researcher
from app.nodes.planner import (
    AGENCY_LABEL,
    DOC_LABEL,
    _field,
    _pick,
    build_task_graph,
    summary,
)
from app.nodes.doc_builder import DocumentIncomplete, render
from app.nodes.profiler import label_of as _label_of
from app.rules.loader import VISA_CODES, actions_for, evidence_labels
from app.tools import llm

KST = timezone.utc  # 표시용. 실제 타임존은 서비스 설정에서 주입한다.

# 도구 루프를 끌 수 있게 둔다. 데모에서 응답이 느리거나 API 가 불안정하면
# 이 값만 내려 기존 단발 RAG 로 돌아간다.
RESEARCH_ENABLED = os.getenv("RESEARCH_ENABLED", "1") not in ("0", "false", "False")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────
# 슬롯 필링 질문 정의 (mappings 완성 전까지 여기서 관리)
# ──────────────────────────────────────────────────────────
# label / hint / options 는 {ko, en}. LLM 이 문장을 만들어 주면 label·hint 는
# 덮이지만 options 는 LLM 을 타지 않으므로 여기 값이 그대로 화면에 나간다.
QUESTIONS: dict[str, dict] = {
    # 등록증이 없으면 체류자격을 알 길이 없다. 여권에는 스티커로 붙어 있지만
    # 추출기가 그 면을 읽지 않으므로 직접 묻는다. 이걸 모르면 Task Graph 가
    # 통째로 비어 아무 안내도 못 한다 — 정작 등록이 가장 급한 사람이다.
    "visa_type": {
        "label": {"ko": "체류자격이 어떻게 되시나요? 여권의 비자에 적혀 있습니다.",
                  "en": "What is your visa status? It is printed on the visa in your passport."},
        "input_type": "select",
        "options": [],          # 런타임에 visa_codes.yaml 로 채운다
        "hint": {"ko": "예: D-2 (유학)", "en": "e.g. D-2 (Student)"},
    },
    "birth_date": {
        "label": {"ko": "생년월일이 어떻게 되시나요?",
                  "en": "What is your date of birth?"},
        "input_type": "text",
        "options": [],
        "hint": {"ko": "YYYY-MM-DD", "en": "YYYY-MM-DD"},
    },
    "entry_date": {
        "label": {"ko": "한국에 언제 입국하셨나요?",
                  "en": "When did you enter Korea?"},
        "input_type": "text",
        "options": [],
        "hint": {"ko": "YYYY-MM-DD — 여권 입국심사인에 찍혀 있습니다",
                 "en": "YYYY-MM-DD — stamped in your passport at entry"},
    },
    "org_name": {
        "label": {"ko": "어느 학교에 재학 중이신가요?",
                  "en": "Which school are you enrolled in?"},
        "input_type": "text",
        "options": [],
        "hint": {"ko": "재학증명서에 적힌 이름 그대로 적어주세요",
                 "en": "As written on your enrollment certificate"},
    },
    "phone_kr": {
        "label": {"ko": "한국에서 쓰시는 전화번호를 알려주세요.",
                  "en": "What is your phone number in Korea?"},
        "input_type": "text",
        "options": [],
    },
    "purpose": {
        "label": {"ko": "이 계좌를 어떤 용도로 쓰실 건가요?",
                  "en": "What will you use this account for?"},
        "input_type": "select",
        "options": [
            {"value": "living_expense",
             "label": {"ko": "생활비", "en": "Living expenses"}},
            {"value": "tuition", "label": {"ko": "학비", "en": "Tuition"}},
            {"value": "salary", "label": {"ko": "급여", "en": "Salary"}},
            {"value": "remittance", "label": {"ko": "송금", "en": "Remittance"}},
        ],
    },
    "income_source": {
        "label": {"ko": "자금은 어디에서 나오나요?",
                  "en": "Where does your money come from?"},
        "input_type": "select",
        "options": [
            {"value": "scholarship", "label": {"ko": "장학금", "en": "Scholarship"}},
            {"value": "family_support",
             "label": {"ko": "가족 지원", "en": "Family support"}},
            {"value": "part_time", "label": {"ko": "아르바이트", "en": "Part-time job"}},
            {"value": "savings", "label": {"ko": "예금·저축", "en": "Savings"}},
        ],
    },
}


def visa_options() -> list[dict]:
    """체류자격 선택지. visa_codes.yaml 이 한 곳의 출처다."""
    return [{"value": code, "label": f"{code} ({name})"}
            for code, name in VISA_CODES.items()]


def _text(value, locale: str) -> str | None:
    """{ko, en} 이면 locale 을 고르고, 평문이면 그대로 둔다."""
    if isinstance(value, dict):
        return value.get(locale) or value.get("en")
    return value


def _options(opts: list[dict], locale: str) -> list[dict]:
    """value 는 기계가 읽으므로 그대로, label 만 고른다."""
    return [{"value": o["value"], "label": _text(o["label"], locale)} for o in opts]


_HANGUL = re.compile(r"[가-힣]")


def _written_locale(text: str, locale: str) -> str | None:
    """LLM 이 실제로 어느 언어로 썼는지. reply_locale 에 그대로 넣는다.

    LLM 은 요청한 언어가 아니라 **질문의 언어**를 따라가는 일이 있다.
    locale=en 인데 한국어로 답한 것을 en 이라고 찍으면 service._localized 가
    번역을 건너뛰어 영어 사용자에게 한국어가 그대로 나간다. 실제 언어를 보고
    어긋나면 None 을 돌려 출구 번역이 살아나게 한다.
    """
    if not text:
        return None
    if locale == "en" and _HANGUL.search(text):
        return None                       # 한국어로 썼다 → 출구에서 번역한다
    return locale

# 액션별 필수 필드 (D2에 mappings/*.yaml 로 이관)
ACTION_FIELDS: dict[str, list[str]] = {
    "alien_registration": ["birth_date", "entry_date", "org_name", "phone_kr"],
    "residence_change": ["birth_date", "phone_kr"],
    "work_activity": ["org_name"],
    "open_bank_account": ["birth_date", "org_name", "phone_kr",
                          "purpose", "income_source"],
}

ACTION_TITLES: dict[str, dict] = {
    "alien_registration": {"ko": "외국인등록 신청서 제출",
                           "en": "Submit Alien Registration application"},
    "residence_change": {"ko": "체류지 변경신고 제출",
                         "en": "Submit Change of Residence report"},
    "work_activity": {"ko": "체류자격외활동허가 신청서 제출",
                      "en": "Submit Activity Permit application"},
    "open_bank_account": {"ko": "계좌개설 신청서 제출",
                          "en": "Submit account opening application"},
}

NO_ID = {"ko": "신분증을 올려주시면 무엇을 하셔야 하는지 알려드릴게요.",
         "en": "Upload your ID and I will tell you what you need to do."}
VISA_LEAD = {"ko": "체류자격만 알면 무엇을 하셔야 하는지 알려드릴 수 있습니다.",
             "en": "Once I know your visa status I can tell you what to do."}
VISA_UNSUPPORTED = {
    "ko": "{} 는 아직 안내를 준비하지 못했습니다. 지금은 D-2(유학)만 "
          "지원합니다. 출입국·외국인종합안내센터(1345)에 문의해주세요.",
    "en": "I do not have guidance for {} yet — only D-2 (Student) for now. "
          "Please call the immigration center at 1345.",
}

OFFLINE_LEAD = {
    "ko": "{}은(는) 앱이 대신 작성할 서류가 없습니다. 직접 방문하셔야 합니다.",
    "en": "There is no form for {} that the app can fill in. You go in person.",
}

SLOT_LEAD = {
    "many": {"ko": "{}가지만 여쭤볼게요 — {}.",
             "en": "Just {} things to ask — {}."},
    "last": {"ko": "마지막 질문입니다.", "en": "Last question."},
}

DOC_MISSING = {"ko": "서류를 작성하려면 {}이(가) 더 필요합니다.",
               "en": "I still need {} to fill in the form."}

# 승인 payload 의 고정 문구. ui.payload 는 번역을 거치지 않으므로 여기서 고른다.
SUMMARY_LABEL: dict[str, dict] = {
    "agency": {"ko": "제출처", "en": "Submit to"},
    "docs": {"ko": "지참 서류", "en": "Bring with you"},
}


def _title(action: str, locale: str) -> str:
    return _text(ACTION_TITLES.get(action), locale) or action

# 답변 뒤에 붙는 근거 표시. 답변 본문은 이미 사용자 언어라 통째로 번역하지 않는다.
CITE_LABEL: dict[str, str] = {"ko": "근거", "en": "Source"}


# ══════════════════════════════════════════════════════════
# 노드
# ══════════════════════════════════════════════════════════
def planner(state: AgentState) -> dict:
    """룰 엔진으로 Task Graph를 계산한다. LLM 없음."""
    # 진입 노드다. 지난 턴의 reply_locale 이 남아 이번 턴 한국어 문구가
    # 번역을 건너뛰는 일이 없도록 여기서 매 턴 지운다.
    profile = state.get("profile", {})
    if not profile.get("visa_type"):
        return {"tasks": [], "reply_locale": None}

    tasks = build_task_graph(
        profile,
        completed=set(state.get("completed", [])),
        in_progress=set(state.get("in_progress", [])),
        locale=state.get("locale") or "en",
    )
    return {"tasks": tasks, "reply_locale": None}


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

    # 정적 문구는 여기서 locale 을 고른다 — 이 payload 는 번역을 거치지 않고 나간다.
    label = _text(q["label"], locale)
    hint = _text(q.get("hint"), locale)
    # 말풍선은 무엇을 물을지 미리 알려 준다. 개수만 말하면 사용자는 몇 번이나
    # 더 답해야 하는지, 무엇을 준비해야 하는지 모른 채 하나씩 끌려간다.
    names = ", ".join(_label_of(f, locale) for f in missing)
    lead = (_text(SLOT_LEAD["many"], locale).format(len(missing), names)
            if len(missing) > 1 else _text(SLOT_LEAD["last"], locale))
    written_locale = locale        # 이미 사용자 언어다 — 번역을 태우지 않는다

    # LLM 은 문장 생성만. 실패해도 흐름이 끊기지 않는다.
    if llm.available():
        written = llm.ask_field(
            field,
            label=_text(q["label"], "en"),      # 필드 뜻 설명용 — 프롬프트는 영어다
            locale=locale,
            context=state.get("profile", {}),
            remaining=len(missing),
        )
        if written and written.get("question"):
            label = written["question"]
            hint = written.get("hint") or hint

    # reply 에는 질문을 넣지 않는다. 질문은 ui.payload.label 이 들고 있고
    # 프론트가 그것으로 질문 카드를 그리므로, 여기에 또 쓰면 같은 문장이
    # 말풍선과 카드에 두 번 보인다. 말풍선은 진행 상황만 알린다.
    return {
        "missing_fields": missing,
        "asked_field": field,
        "reply": lead,
        "reply_locale": written_locale,
        "ui_type": "question",
        "ui_payload": {
            "field": field,
            "label": label,
            "input_type": q["input_type"],
            "options": _options(q.get("options", []), locale),
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
        # 앱이 만들 서식이 없는 과제다(통신 가입 등). 여기까지 왔다는 것은
        # 어딘가에서 "시작할까요" 를 물었다는 뜻인데, 시작할 것이 없다.
        #
        # 예전에는 "이 단계는 서류 없이 진행됩니다" 한 줄만 돌려주고
        # current_action 을 남겨 두었다. 그러면 무슨 말을 하든 router 가
        # 다시 이 자리로 보내 같은 문장만 반복됐다 — 빠져나갈 수 없었다.
        return {"current_action": None, "in_progress": [],
                **_offline_guidance(state, action, spec)}

    try:
        result = render(
            form,
            profile,
            confidence=state.get("confidence", {}),
            variant=spec.get("form_type", "default"),
            required_docs=spec.get("required_docs", []),
            account_type=spec.get("account_type", "limited"),
            doc_id=f"{state['session_id']}-{action}",
            locale=state.get("locale") or "en",
        )
    except DocumentIncomplete as exc:
        # 라벨 사전을 여기 또 두면 profiler.LABELS 와 어긋난다. 실제로 어긋나
        # stay_expiry 가 사람 말 대신 키 이름 그대로 화면에 나갔다.
        locale = state.get("locale") or "en"
        need = ", ".join(_label_of(k, locale) for k in exc.missing)
        return {
            "missing_fields": exc.missing,
            "reply": _text(DOC_MISSING, locale).format(need),
            "reply_locale": locale,
            "ui_type": "none",
            "ui_payload": {},
        }

    # PDF 가 안 만들어졌는데 pdf_url 을 내보내면 백엔드는 404 를 받는다.
    # render() 는 실패를 삼키고 pdf_path=None 으로 돌려주므로 여기서 걸러낸다.
    # 원인은 대개 배포 환경에 WeasyPrint 의 네이티브 의존성이 없는 것이다.
    if not result.get("pdf_path"):
        return {
            "reply": "서류 생성에 실패했습니다. 잠시 후 다시 시도해주세요.",
            "ui_type": "none",
            "ui_payload": {},
            "pending_approval": None,
        }

    doc = {
        "id": result["document_id"],
        "title": result["title"],
        "action_id": action,
        "preview_url": f"/api/documents/{result['document_id']}/preview",
        "pdf_url": f"/api/documents/{result['document_id']}.pdf",
        "created_at": _now(),
    }

    locale = state.get("locale") or "en"
    warn_tpl = ("{} 값을 한 번 확인해주세요" if locale == "ko"
                else "Please double-check {}")
    warnings = [warn_tpl.format(_label_of(k, locale))
                for k in result["low_confidence"]]

    docs = [_pick(DOC_LABEL, d, locale, d) for d in spec.get("required_docs", [])]
    agency = _pick(AGENCY_LABEL, spec.get("agency", ""), locale,
                   spec.get("agency", ""))

    summary_lines = [_title(action, locale)]
    if agency:
        summary_lines.append(f"{_text(SUMMARY_LABEL['agency'], locale)} · {agency}")
    if docs:
        summary_lines.append(f"{_text(SUMMARY_LABEL['docs'], locale)} · "
                             + ", ".join(docs))

    pending = {
        "action_id": action,
        "title": _title(action, locale),
        "summary": summary_lines,
        "document_id": doc["id"],
        "doc_title": doc["title"],              # 서류 이름 — 액션 제목(title)과 다르다
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


def _offline_guidance(state: AgentState, action: str, spec: dict) -> dict:
    """앱이 대신 해 줄 것이 없는 과제의 안내. 무엇을 들고 어디로 갈지 말한다."""
    locale = state.get("locale") or "en"
    task = next((t for t in (state.get("tasks") or []) if t["id"] == action), None)
    label = _title(action, locale) if action in ACTION_TITLES else (
        task["label"] if task else action)

    lines = [_text(OFFLINE_LEAD, locale).format(label)]
    agency = _pick(AGENCY_LABEL, spec.get("agency", ""), locale)
    if agency:
        lines.append(f"{_text(SUMMARY_LABEL['agency'], locale)} · {agency}")
    docs = [_pick(DOC_LABEL, d, locale, d) for d in spec.get("required_docs", [])]
    if docs:
        lines.append(f"{_text(SUMMARY_LABEL['docs'], locale)} · " + ", ".join(docs))
    if note := _field(spec, "note", locale):
        lines.append(note)

    return {"reply": "\n".join(lines), "reply_locale": locale,
            "ui_type": "none", "ui_payload": {}}


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

    # 서류가 만들어졌으면 화면은 서류 미리보기를 유지한다.
    # 백엔드가 ui.type == "doc_preview" 일 때만 PDF 를 내려받아 저장하므로,
    # 여기서 approval 로 덮으면 PDF 가 영영 저장되지 않는다.
    # 승인 정보는 state.pending_approval 로 나가고, 화면은 그것도 함께 본다.
    if pending.get("document_id"):
        return {
            "reply": "아래 내용을 실행할까요?",
            "ui_type": "doc_preview",
            "ui_payload": {
                "document_id": pending["document_id"],
                "title": pending.get("doc_title") or pending.get("title", ""),
                "preview_url": pending.get("preview_url", ""),
                "pdf_url": pending.get("pdf_url", ""),
                "warnings": pending.get("warnings", []),
            },
        }

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
    # 이 노드의 문구는 reply 로만 나간다 — 한국어로 쓰고 출구에서 번역한다.
    agency = _pick(AGENCY_LABEL, spec.get("agency", ""), "ko", "담당 기관")

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

    lines = [f"{_title(action, 'ko')} 작성이 끝났습니다.",
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
    """자유 질문에 답하거나, 없으면 상황을 안내한다."""
    tasks = state.get("tasks") or []
    locale = state.get("locale", "en")

    # 자유 질문일 때만 법령 검색을 탄다. 슬롯 필링 답변은 질문이 아니다.
    last = state.get("ask")

    if last and last != state.get("last_qa") and qa.available():
        profile = state.get("profile", {})
        history = state.get("messages") or []

        # 도구 루프를 먼저 태운다. 모델이 무엇을 몇 번 조회할지 스스로 정하므로
        # 과제 상태와 법령을 함께 봐야 하는 질문에 강하다. 실패하면 아래
        # 단발 RAG 로 내려간다 — 대화가 끊기지 않는 게 우선이다.
        got = None
        if RESEARCH_ENABLED and researcher.available():
            got = researcher.answer(last, profile=profile, tasks=tasks,
                                    history=history, locale=locale)
            if got and got.get("trace"):
                print("[researcher] " + " → ".join(t["tool"] for t in got["trace"]))

        if got is None:
            got = qa.answer(last, profile=profile,
                            tasks=tasks, history=history,
                            locale=locale)
        if got:
            reply = got["reply"]
            if got["cites"]:
                reply += f"\n\n{CITE_LABEL.get(locale, CITE_LABEL['en'])} · " \
                         + " / ".join(got["cites"])
            out = {"reply": reply,
                   "reply_locale": _written_locale(got["reply"], locale),
                   "ui_type": "none", "last_qa": last, "ask": None}
            # 모델이 "시작할까요" 로 끝냈으면 다음 턴의 "ㅇㅇ" 이 붙을 자리를
            # 남겨 둔다. 없으면 승낙이 새 질문으로 흘러간다.
            offer = got.get("offer") or _implied_offer(got["reply"], tasks)
            if offer:
                out["pending_offer"] = offer
            return out
        base = ("제가 가진 법령 자료로는 확인이 어렵습니다. "
                "출입국·외국인종합안내센터(1345)나 은행 창구에 확인해주세요.")
        return {"reply": base, "ui_type": "none", "last_qa": last, "ask": None}

    if not tasks:
        return ask_visa(state)

    base = summary(tasks)

    if llm.available():
        nxt = _next_action(tasks)
        spoken = llm.explain({
            "available_count": sum(1 for t in tasks if t["status"] == "available"),
            "next_action_label": nxt["label"] if nxt else None,
            "next_action_agency": nxt.get("agency") if nxt else None,
            "next_action_documents": nxt.get("required_docs") if nxt else [],
            "d_day": nxt["d_day"] if nxt else None,
            "blocked": [{"label": t["label"], "blocked_by": t["blocked_by"]}
                        for t in tasks if t["status"] == "locked"][:3],
            "evidence": nxt["evidence"] if nxt else [],
            "call_to_action": (f'Tell the user to tap the "{nxt["label"]}" card to start.'
                               if nxt else None),
        }, locale=locale)
        if spoken:
            return {"reply": spoken,
                    "reply_locale": _written_locale(spoken, locale),
                    "ui_type": "none"}

    return {"reply": base, "ui_type": "none"}

# 사용자의 목표를 우선한다. 조건부 액션(체류지 변경 등)은 스스로 권하지 않는다.
NEXT_PRIORITY = ["open_bank_account", "alien_registration", "mobile_subscription"]


def _implied_offer(reply: str, tasks: list[dict]) -> dict | None:
    """모델이 물음표로 끝냈는데 offer_to_start 를 부르지 않았을 때의 안전망.

    프롬프트로 도구 호출을 강제해 봤지만 모델이 종종 빠뜨린다. 그러면 사용자의
    "ㅇㅇ" 이 붙을 자리가 없어 대화가 막힌다. 물음표로 끝났다는 것은 무언가를
    물었다는 뜻이므로, 지금 시작할 수 있는 과제를 붙여 둔다.

    틀려도 열리는 것은 과제뿐이다 — 부작용이 없고 되돌릴 수 있다. 실행은
    여전히 approval_gate 를 지난다.
    """
    if not reply.rstrip().endswith(("?", "？")):
        return None
    nxt = _next_action(tasks)
    if not nxt:
        return None
    return {"kind": "start_action", "action_id": nxt["id"], "label": nxt["label"]}


def ask_visa(state: AgentState) -> dict:
    """체류자격을 몰라 아무 안내도 못 하는 상태를 푼다.

    무엇을 올렸느냐로 갈린다.
      아무것도 없음        → 신분증부터 받는다
      여권만 있음          → 체류자격을 묻는다. 등록하러 온 사람에게
                            등록증을 가져오라고 하면 안 된다.
      자격은 아는데 미지원  → 솔직히 말한다. 없는 안내를 지어내지 않는다.
    """
    locale = state.get("locale") or "en"
    profile = state.get("profile") or {}

    if not profile:
        return {"reply": _text(NO_ID, locale), "reply_locale": locale,
                "ui_type": "none"}

    visa = profile.get("visa_type")
    if visa and not actions_for(visa):
        return {"reply": _text(VISA_UNSUPPORTED, locale).format(visa),
                "reply_locale": locale, "ui_type": "none"}

    q = QUESTIONS["visa_type"]
    return {
        "asked_field": "visa_type",
        "reply": _text(VISA_LEAD, locale),
        "reply_locale": locale,
        "ui_type": "question",
        "ui_payload": {
            "field": "visa_type",
            "label": _text(q["label"], locale),
            "input_type": "select",
            "options": visa_options(),
            "hint": _text(q["hint"], locale),
        },
    }


def _next_action(tasks: list[dict]) -> dict | None:
    """지금 먼저 권할 액션. 우선순위에 없는 조건부 액션은 권하지 않는다."""
    avail = [t for t in tasks if t["status"] == "available"]
    return next((t for a in NEXT_PRIORITY for t in avail if t["id"] == a), None)


def ledger_writer(state: AgentState) -> dict:
    """Executor 이후 Task Graph를 다시 계산하고, 새로 열린 일을 알린다."""
    out = planner(state)
    tasks = out.get("tasks") or []

    nxt = _next_action(tasks)
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
