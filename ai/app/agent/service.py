"""Agent Service — FS-2 가 쓰는 유일한 진입점.

LangGraph 를 몰라도 이 파일의 invoke() 하나만 알면 된다.
반환값은 api/schemas.py 의 AgentResponse 와 1:1 이다.
"""
from __future__ import annotations

import os
import uuid
from functools import lru_cache
from typing import Any, ClassVar, Literal, Optional

from app.agent.graph import build_graph
from app.agent.state import new_state
from app.nodes.doc_builder import CONF_THRESHOLD
from app.nodes.planner import MENU_TITLE, menu_options, summary
from app.nodes.profiler import (
    HARD_KEYS,
    SOFT_KEYS,
    conflicts,
    profile_to_payload,
    public_profile,
)
from app.nodes.profiler import run as profiler_run
from app.tools import llm

DocType = Literal["arc_front", "arc_back", "passport"]


# ──────────────────────────────────────────────────────────
# 그래프 · 체크포인터 (프로세스당 1회 초기화)
# ──────────────────────────────────────────────────────────
# 커넥션을 모듈 전역에 붙잡아 둔다.
# from_conn_string() 의 컨텍스트 매니저를 지역 변수로 두면 GC 시점에
# 커넥션이 닫혀 "the connection is closed" 가 난다.
_CONN = None


def _make_checkpointer():
    global _CONN

    url = os.getenv("DATABASE_URL")
    if url:
        try:
            from psycopg import Connection
            from psycopg.rows import dict_row
            from langgraph.checkpoint.postgres import PostgresSaver

            _CONN = Connection.connect(
                url,
                autocommit=True,        # checkpointer 는 자체 트랜잭션을 쓰지 않는다
                prepare_threshold=0,
                row_factory=dict_row,
            )
            cp = PostgresSaver(_CONN)
            cp.setup()                  # 테이블 자동 생성 (idempotent)
            print("[agent] Postgres checkpointer 연결됨")
            return cp
        except Exception as exc:        # noqa: BLE001
            print(f"[agent] Postgres checkpointer 실패, 메모리로 대체: {exc!r}")
            if _CONN is not None:
                try:
                    _CONN.close()
                except Exception:       # noqa: BLE001
                    pass
                _CONN = None

    from langgraph.checkpoint.memory import MemorySaver
    print("[agent] MemorySaver 사용 (재시작 시 세션 소멸)")
    return MemorySaver()


@lru_cache(maxsize=1)
def _graph():
    return build_graph(checkpointer=_make_checkpointer())


def is_persistent() -> bool:
    """Checkpointer를 초기화하고 Postgres 연결 상태를 반환한다.

    배포 직후에도 /health가 실제 RDS 연결을 검증해야 하므로,
    첫 Agent 요청을 기다리지 않고 그래프를 여기서 초기화한다.
    """
    _graph()
    return _CONN is not None and not _CONN.closed


def _cfg(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _seen(session_id: str) -> bool:
    """이 세션의 체크포인트가 이미 있는지."""
    try:
        return _graph().get_state(_cfg(session_id)).values != {}
    except Exception:                              # noqa: BLE001
        return False


# ──────────────────────────────────────────────────────────
# 응답 조립
# ──────────────────────────────────────────────────────────
def _localized(state: dict, reply: str | None, reply_locale: str | None) -> str:
    """사용자 언어로 맞춘 reply.

    노드와 이 모듈의 문구는 대부분 한국어 리터럴이다. 열 몇 군데에 번역을
    흩어 놓는 대신 나가는 길목 한 곳에서 옮긴다. LLM 이 이미 사용자 언어로
    쓴 문장만 reply_locale 이 찍혀 있어 번역을 건너뛴다 — 노드는 state 에,
    이 모듈은 인자로 알린다.
    """
    locale = state.get("locale") or "en"
    written = reply_locale if reply is not None else state.get("reply_locale")
    text = reply if reply is not None else (state.get("reply") or "")
    if not text or written == locale:
        return text
    return llm.translate(text, locale)      # locale==ko 이거나 LLM 없으면 원문


def locale_of(session_id: str) -> str:
    """세션의 표시 언어. 세션이 아직 없으면 앱 기본값."""
    if not _seen(session_id):
        return "en"
    return _graph().get_state(_cfg(session_id)).values.get("locale") or "en"


def localize_message(session_id: str, message: str) -> str:
    """사용자에게 보이는 오류 문구를 세션 언어로 옮긴다.

    reply 와 같은 규칙이다 — 문구는 한국어로 쓰고 나가는 길목에서 옮긴다.
    """
    locale = locale_of(session_id)
    if not message or locale == "ko":
        return message
    return llm.translate(message, locale)


def localize_error(session_id: str, detail: dict) -> dict:
    """오류 detail 의 message 만 옮긴다.

    error 코드와 details 는 기계가 읽으므로 건드리지 않는다.
    """
    message = detail.get("message") or ""
    if not message:
        return detail
    return {**detail, "message": localize_message(session_id, message)}


def _response(state: dict, reply: str | None = None,
              ui_type: str | None = None, ui_payload: dict | None = None,
              reply_locale: str | None = None) -> dict:
    """reply_locale 은 reply 인자가 이미 어느 언어로 쓰였는지. 기본값은 한국어."""
    return {
        "schema_version": "1",
        "reply": _localized(state, reply, reply_locale),
        "ui": {
            "type": ui_type or state.get("ui_type") or "none",
            "payload": ui_payload if ui_payload is not None
            else (state.get("ui_payload") or {}),
        },
        "state": {
            "session_id": state.get("session_id", ""),
            "locale": state.get("locale", "en"),
            "profile": public_profile(state.get("profile", {})),
            "tasks": state.get("tasks", []),
            "documents": state.get("documents", []),
            "pending_approval": state.get("pending_approval"),
        },
    }


def _patch(session_id: str, extra: dict[str, Any]) -> dict:
    """첫 턴이면 초기 상태를, 이후엔 변경분만 넘긴다."""
    if _seen(session_id):
        return extra
    base = dict(new_state(session_id))
    base.update(extra)
    return base


# ──────────────────────────────────────────────────────────
# public API
# ──────────────────────────────────────────────────────────
def start_session(session_id: str | None = None, locale: str = "en") -> dict:
    """session_id 를 주면 그 세션을 이어받고, 없으면 새 세션을 만든다.

    데모 대본용으로 고정 id 를 쓰고 싶으면 명시적으로 넘긴다.
    """
    sid = session_id or f"s-{uuid.uuid4().hex[:10]}"
    state = _graph().invoke(_patch(sid, {"locale": locale}), _cfg(sid))

    # 첫 화면의 말문. 여기서 무엇을 할 수 있는지 알려주지 않으면 사용자는
    # 빈 입력창 앞에서 아무 말도 못 한다. 이어받은 세션은 인사하지 않는다 —
    # 새로고침할 때마다 자기소개를 다시 하면 이상하다.
    if not state.get("messages"):
        return _response(state, _pick(GREETING, "new", locale), "none", {},
                         reply_locale=locale)
    return _response(state)


def extract(session_id: str, image: bytes, doc_type: DocType,
            ext: str = "jpg") -> dict:
    """신분증 → 프로필 갱신 → Task Graph 재계산."""
    holder: dict = {"profile": {}, "confidence": {}}
    holder, payload = profiler_run(holder, image, doc_type, ext=ext)
    incoming = holder["profile"]

    # 이미 쌓인 프로필과 대조한다. 병합은 나중 값이 이기므로, 여기서 막지
    # 않으면 다른 사람의 서류가 조용히 섞여 한 프로필이 된다.
    snap = _graph().get_state(_cfg(session_id)).values if _seen(session_id) else {}
    existing = snap.get("profile") or {}

    if hard := conflicts(existing, incoming, HARD_KEYS):
        raise IdentityMismatch(doc_type, hard)

    # 이름은 표기가 갈릴 수 있어 거부하지 않는다. 대신 확인 대상으로 내린다.
    soft = conflicts(existing, incoming, SOFT_KEYS)
    for key in soft:
        holder["confidence"][key] = 0.50

    state = _graph().invoke(_patch(session_id, {
        "profile": holder["profile"],
        "confidence": holder["confidence"],
        "raw_texts": holder.get("raw_texts", []),
        "dropped": holder.get("dropped", []),
    }), _cfg(session_id))

    # 누적된 전체 프로필 기준으로 확인 카드를 다시 만든다
    payload = profile_to_payload(state.get("profile", {}),
                                 state.get("confidence", {}), doc_type,
                                 locale=state.get("locale") or "en")

    low = [f["key"] for f in payload["fields"]
           if f["confidence"] < CONF_THRESHOLD]
    head = ("신분증을 확인했습니다." if not low else
            f"신분증을 확인했습니다. {len(low)}개 항목은 확인이 필요합니다.")
    if soft:
        head += ("\n서류마다 이름 표기가 다릅니다. "
                 "여권과 같은 표기로 맞춰주세요.")
    tasks = state.get("tasks") or []
    reply = f"{head}\n{summary(tasks)}" if tasks else head

    return _response(state, reply, "profile_confirm", payload)


def apply_profile_edits(session_id: str, edits: dict) -> dict:
    """확인 화면에서 고친 값 반영. 마스킹된 값은 무시된다."""
    import re
    masked = re.compile(r"\*{3,}")
    clean = {k: v for k, v in (edits or {}).items()
             if v not in (None, "") and not masked.search(str(v))}

    state = _graph().invoke(_patch(session_id, {"profile": clean}), _cfg(session_id))
    return _response(state)


# 슬롯 필링 필드의 의미와 허용값 (graph.QUESTIONS 와 짝)
_FIELD_META = {
    "birth_date":    ("Date of birth (YYYY-MM-DD)", None),
    "entry_date":    ("Date of entry into Korea (YYYY-MM-DD)", None),
    "entry_date":    ("Date of entry into Korea (YYYY-MM-DD)", None),
    "org_name":      ("Name of the school or organization", None),
    "phone_kr":      ("Phone number in Korea", None),
    "purpose":       ("Purpose of the bank account",
                      {"living_expense": 1, "tuition": 1, "salary": 1, "remittance": 1}),
    "income_source": ("Source of funds",
                      {"scholarship": 1, "family_support": 1, "part_time": 1, "savings": 1}),
}


# ──────────────────────────────────────────────────────────
# 자유 발화 라우팅
# ──────────────────────────────────────────────────────────
# 승인(실행)은 여기 없다. 채팅으로 할 수 있는 것은 "과제를 연다" 까지고,
# 되돌릴 수 없는 행동은 approval_gate 의 명시적 승인으로만 나간다.
_OFFER_TEXT = {
    "start_action": "Start the task now?",
    "menu": "Pick one from the menu.",
}

GREETING = {
    "new": {
        "ko": "안녕하세요. 한국 정착에 필요한 일들을 함께 처리하는 도우미입니다.\n"
              "체류·계좌·통신 무엇이든 물어보세요. "
              "지금 뭘 해야 할지 모르겠으면 \"메뉴\"라고 말씀해주세요.",
        "en": "Hello. I help you get settled in Korea.\n"
              "Ask me anything about your visa, bank account, or phone. "
              "If you are not sure where to start, just say \"menu\".",
    },
}

_ACK = {
    "no":      {"ko": "알겠습니다. 필요하시면 언제든 말씀해주세요.",
                "en": "Alright. Tell me whenever you need it."},
    "unclear": {"ko": "시작할까요? '네' 또는 '아니요' 로 답해주세요.",
                "en": "Shall I start? Please answer yes or no."},
    "done":    {"ko": "{}은(는) 이미 완료하셨습니다.",
                "en": "You have already completed {}."},
    "nothing": {"ko": "지금 하실 수 있는 일이 없습니다.",
                "en": "There is nothing to do right now."},
    # 할 일이 없는 것과 아직 모르는 것은 다르다. 프로필이 비었는데 "없습니다"
    # 라고 하면 사용자는 앱이 고장 났다고 생각한다.
    "no_profile": {"ko": "외국인등록증을 먼저 촬영해주세요. "
                         "체류자격을 알아야 무엇을 하셔야 하는지 알려드릴 수 있습니다.",
                   "en": "Please photograph your residence card first. "
                         "I need your visa status before I can tell you what to do."},
}


def _pick(table: dict, key: str, locale: str) -> str:
    return table[key].get(locale) or table[key]["en"]


def _task(tasks: list[dict], action_id: str) -> dict | None:
    return next((t for t in tasks if t["id"] == action_id), None)


def _offer_start(task: dict, locale: str) -> tuple[str, dict]:
    """과제 하나를 권하는 문구와, 다음 턴에 'ㅇㅇ' 을 해석할 근거를 만든다."""
    bits = [f"{task['label']}부터 하셔야 합니다."
            if task["status"] == "locked" else f"{task['label']}을(를) 하실 수 있습니다."]
    if task.get("agency"):
        bits.append(f"제출처는 {task['agency']}입니다.")
    if task.get("deadline"):
        d = task.get("d_day")
        if d is not None and d < 0:
            bits.append(f"기한 {task['deadline']}에서 {abs(d)}일 지났습니다.")
        elif d is not None:
            bits.append(f"기한은 {task['deadline']}, {d}일 남았습니다.")
    if task.get("required_docs"):
        bits.append("지참 서류는 " + ", ".join(task["required_docs"]) + "입니다.")
    bits.append("지금 시작할까요?")
    offer = {"kind": "start_action", "action_id": task["id"], "label": task["label"]}
    return " ".join(bits), offer


def _blocking(tasks: list[dict], task: dict) -> dict:
    """잠긴 과제를 풀어 줄, 지금 할 수 있는 선행 과제. 없으면 자기 자신."""
    for pid in task.get("prereq", []):
        p = _task(tasks, pid)
        if p and p["status"] != "done":
            return p if p["status"] != "locked" else _blocking(tasks, p)
    return task


def send_message(session_id: str, message: str) -> dict:
    """대화 입력.

    슬롯 필링 중이면 LLM 이 자유 발화에서 값을 뽑는다.
    추출 실패 시 프로필을 건드리지 않고 되묻는다 — 쓰레기 값이 서류로 가지 않는다.
    """
    snap = _graph().get_state(_cfg(session_id)).values if _seen(session_id) else {}
    asked = snap.get("asked_field")

    extra: dict[str, Any] = {"messages": [{"role": "user", "content": message}]}

    if asked:
        value, failed, failed_locale = message.strip(), None, None
        locale = snap.get("locale") or "en"

        if llm.available():
            label, enum = _FIELD_META.get(asked, (asked, None))
            parsed = llm.parse_answer(asked, label=label, message=message,
                                      enum=enum, locale=locale)
            if parsed is None:
                pass                                  # LLM 실패 → 원문 사용
            elif parsed.get("ok") and parsed.get("value"):
                value = parsed["value"]
            elif parsed.get("reason"):
                # reason 은 parse_answer 가 사용자 언어로 쓴다. 다시 번역하지 않는다.
                failed, failed_locale = parsed["reason"].strip(), locale
            else:
                failed = "값을 알아듣지 못했습니다."

        if failed:
            # 같은 필드를 다시 묻는다. asked_field 를 유지한다.
            state = _graph().get_state(_cfg(session_id)).values
            return _response(state, failed, "question",
                             state.get("ui_payload") or {},
                             reply_locale=failed_locale)

        extra["profile"] = {asked: value}
        extra["asked_field"] = None
        state = _graph().invoke(_patch(session_id, extra), _cfg(session_id))
        return _response(state)

    # ── 자유 발화 ──────────────────────────────────────────
    locale = snap.get("locale") or "en"
    tasks = snap.get("tasks") or []
    offer = snap.get("pending_offer") or {}

    # 메뉴에서 고른 값은 그대로 돌아온다. 확실한 것을 LLM 에 물을 이유가 없다.
    picked = message.strip()
    if offer.get("kind") == "menu" and picked in (offer.get("options") or []):
        return _guide(session_id, extra, tasks, picked, locale)

    intent = llm.classify(
        message,
        actions=[t["id"] for t in tasks],
        offer=_OFFER_TEXT.get(offer.get("kind")) if offer else None,
    ) or {}
    kind = intent.get("intent")

    # 1. 물어둔 제안에 대한 대답
    if offer and kind == "confirm":
        if intent.get("yes") is True:
            if offer.get("kind") == "start_action":
                return _begin(session_id, extra, offer["action_id"], locale)
        elif intent.get("yes") is False:
            extra["pending_offer"] = None
            state = _graph().invoke(_patch(session_id, extra), _cfg(session_id))
            return _response(state, _pick(_ACK, "no", locale), "none", {},
                             reply_locale=locale)
        # yes 가 None 이면 애매하다는 뜻이다. 실행하지 않고 다시 묻는다.
        state = _graph().invoke(_patch(session_id, extra), _cfg(session_id))
        return _response(state, _pick(_ACK, "unclear", locale), "none", {},
                         reply_locale=locale)

    # 2. 메뉴 요청
    if kind == "menu":
        return _menu(session_id, extra, locale)

    # 3. 특정 과제를 하겠다는 요청
    if kind == "action" and intent.get("action_id"):
        return _guide(session_id, extra, tasks, intent["action_id"], locale)

    # 4. 나머지는 질의응답으로 보낸다
    extra["ask"] = message
    extra["pending_offer"] = None
    state = _graph().invoke(_patch(session_id, extra), _cfg(session_id))
    return _response(state)


def _menu(session_id: str, extra: dict, locale: str) -> dict:
    """지금 이 사람이 할 수 있는 일을 select 로 내린다."""
    state = _graph().invoke(_patch(session_id, extra), _cfg(session_id))
    options = menu_options(state.get("tasks") or [], locale)
    if not options:
        key = "nothing" if (state.get("profile") or {}).get("visa_type") \
              else "no_profile"
        return _response(state, _pick(_ACK, key, locale), "none", {},
                             reply_locale=locale)

    state = _graph().invoke(
        _patch(session_id, {"pending_offer": {
            "kind": "menu", "options": [o["value"] for o in options]}}),
        _cfg(session_id))
    title = MENU_TITLE.get(locale) or MENU_TITLE["en"]
    return _response(state, title, "question", {
        "field": "menu",
        "label": title,
        "input_type": "select",
        "options": options,
        "hint": None,
    }, reply_locale=locale)


def _guide(session_id: str, extra: dict, tasks: list[dict],
           action_id: str, locale: str) -> dict:
    """과제 하나에 대한 안내. 상태에 따라 답이 갈린다."""
    task = _task(tasks, action_id)
    if task is None:                      # 이 체류자격에 없는 과제
        extra["ask"] = action_id
        state = _graph().invoke(_patch(session_id, extra), _cfg(session_id))
        return _response(state)

    if task["status"] == "done":
        extra["pending_offer"] = None
        state = _graph().invoke(_patch(session_id, extra), _cfg(session_id))
        return _response(state,
                         _pick(_ACK, "done", locale).format(task["label"]),
                         "none", {}, reply_locale=locale)

    # 잠겼으면 풀어 줄 선행 과제를 권한다. 사용자가 원한 것을 기억해 두지 않아도
    # 선행이 끝나면 planner 가 다시 available 로 올려 준다.
    target = _blocking(tasks, task) if task["status"] == "locked" else task
    reply, offer = _offer_start(target, locale)
    if target["id"] != task["id"]:
        reply = f"{task['label']}은(는) 아직 잠겨 있습니다. " + reply

    extra["pending_offer"] = offer
    state = _graph().invoke(_patch(session_id, extra), _cfg(session_id))
    return _response(state, reply, "none", {})


def _begin(session_id: str, extra: dict, action_id: str, locale: str) -> dict:
    """승낙받은 과제를 연다. 여기서 실행되는 것은 없다 — 부족한 값을 묻기 시작할 뿐이다."""
    extra.update({
        "current_action": action_id,
        "in_progress": [action_id],
        "pending_offer": None,
    })
    state = _graph().invoke(_patch(session_id, extra), _cfg(session_id))
    return _response(state)


def start_action(session_id: str, action_id: str) -> dict:
    """액션 시작. 잠긴 액션이면 PrerequisiteMissing 을 던진다."""
    snap = _graph().get_state(_cfg(session_id)).values if _seen(session_id) else {}
    task = next((t for t in snap.get("tasks", []) if t["id"] == action_id), None)

    if task and task["status"] == "locked":
        raise PrerequisiteMissing(action_id, task.get("blocked_by", []),
                                  task.get("prereq", []))

    state = _graph().invoke(_patch(session_id, {
        "current_action": action_id,
        "in_progress": [action_id],
    }), _cfg(session_id))
    return _response(state)


def preview_action(session_id: str, action_id: str) -> dict:
    """서류를 생성하고 승인 대기 상태로 만든다.

    start_action 과 나뉘어 있다 — start 는 액션을 열고 부족한 값을 묻는 단계,
    preview 는 값이 다 모인 뒤 실제로 서류를 만드는 단계다. 백엔드는 이 응답의
    ui.type == "doc_preview" 를 보고 PDF 를 내려받아 저장한다.

    아직 답하지 않은 필드가 남아 있으면 서류를 만들지 않고 그 질문을 돌려준다.
    이때 ui.type 은 "question" 이므로 백엔드는 저장 단계로 넘어가지 않는다.
    """
    snap = _graph().get_state(_cfg(session_id)).values if _seen(session_id) else {}
    task = next((t for t in snap.get("tasks", []) if t["id"] == action_id), None)

    if task and task["status"] == "locked":
        raise PrerequisiteMissing(action_id, task.get("blocked_by", []),
                                  task.get("prereq", []))

    # 이미 다른 액션이 승인을 기다리고 있으면 그래프가 그쪽 게이트로 빠진다.
    # 요청한 액션의 서류를 만들러 왔으므로 대기 중인 것을 비우고 다시 세운다.
    extra: dict[str, Any] = {
        "current_action": action_id,
        "in_progress": [action_id],
    }
    pending = snap.get("pending_approval") or {}
    if pending and pending.get("action_id") != action_id:
        extra["pending_approval"] = None
        extra["approval_decision"] = None

    state = _graph().invoke(_patch(session_id, extra), _cfg(session_id))
    return _response(state)


def approve(session_id: str, action_id: str, approved: bool = True) -> dict:
    """승인은 대기 중인 바로 그 액션에만 적용된다.

    path 의 action_id 를 검증하지 않으면 A 를 승인한 요청으로 B 가 실행된다.
    승인 게이트가 "무엇을" 승인했는지 확인하지 않으면 게이트가 아니다.
    """
    snap = _graph().get_state(_cfg(session_id)).values if _seen(session_id) else {}
    pending = snap.get("pending_approval") or {}

    if not pending:
        raise NothingToApprove(action_id)
    if pending.get("action_id") != action_id:
        raise ApprovalMismatch(action_id, pending.get("action_id"))

    state = _graph().invoke(_patch(session_id, {
        "approval_decision": "approve" if approved else "reject",
    }), _cfg(session_id))
    return _response(state)


def get_ledger(session_id: str) -> list[dict]:
    if not _seen(session_id):
        return []
    return _graph().get_state(_cfg(session_id)).values.get("ledger", [])


def get_state(session_id: str) -> dict:
    snap = _graph().get_state(_cfg(session_id)).values if _seen(session_id) else {}
    return _response(snap or new_state(session_id))


# ──────────────────────────────────────────────────────────
# 예외
# ──────────────────────────────────────────────────────────
class IdentityMismatch(Exception):
    """올린 서류의 신원이 이미 등록된 것과 다르다.

    재촬영으로 해결되지 않는다 — 다른 사람의 서류이거나, 앞서 올린 것이
    잘못됐다는 뜻이다. 어느 항목이 어떻게 다른지 알려준다.
    """

    LABELS: ClassVar[dict[str, str]] = {
        "birth_date": "생년월일", "nationality": "국적", "gender": "성별"}

    def __init__(self, doc_type: str, mismatched: dict[str, tuple[str, str]]):
        self.doc_type = doc_type
        self.mismatched = mismatched
        super().__init__(f"identity mismatch: {sorted(mismatched)}")

    def detail(self) -> dict:
        items = ", ".join(
            f"{self.LABELS.get(k, k)}({old} → {new})"
            for k, (old, new) in sorted(self.mismatched.items()))
        return {
            "error": "validation_failed",
            "message": (f"앞서 등록한 신분증과 정보가 다릅니다: {items}. "
                        "같은 사람의 서류가 맞는지 확인해주세요."),
            "details": {
                "doc_type": self.doc_type,
                "mismatched": {k: {"existing": o, "incoming": n}
                               for k, (o, n) in self.mismatched.items()},
            },
        }


class NothingToApprove(Exception):
    """승인 대기 중인 액션이 없다. 이미 처리됐거나 순서가 어긋났다."""

    def __init__(self, action_id: str):
        self.action_id = action_id
        super().__init__(f"nothing pending approval: {action_id}")

    def detail(self) -> dict:
        return {
            "error": "validation_failed",
            "message": "승인을 기다리는 작업이 없습니다. 화면을 새로고침해주세요.",
            "details": {"action_id": self.action_id},
        }


class ApprovalMismatch(Exception):
    """승인 요청의 액션과 대기 중인 액션이 다르다."""

    def __init__(self, requested: str, pending: str | None):
        self.requested = requested
        self.pending = pending
        super().__init__(f"approval mismatch: requested={requested} pending={pending}")

    def detail(self) -> dict:
        return {
            "error": "validation_failed",
            "message": "승인 대상이 화면과 다릅니다. 화면을 새로고침해주세요.",
            "details": {"requested": self.requested, "pending": self.pending},
        }


class PrerequisiteMissing(Exception):
    def __init__(self, action_id: str, blocked_by: list[str], prereq: list[str]):
        self.action_id = action_id
        self.blocked_by = blocked_by
        self.prereq = prereq
        super().__init__(f"prerequisite missing: {', '.join(blocked_by)}")

    def detail(self) -> dict:
        return {
            "error": "prerequisite_missing",
            "message": f"먼저 완료해야 합니다: {', '.join(self.blocked_by)}",
            "details": {"action_id": self.action_id, "prereq": self.prereq},
        }
