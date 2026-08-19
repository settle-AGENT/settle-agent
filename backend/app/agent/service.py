"""Agent Service — FS-2 가 쓰는 유일한 진입점.

LangGraph 를 몰라도 이 파일의 invoke() 하나만 알면 된다.
반환값은 api/schemas.py 의 AgentResponse 와 1:1 이다.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Literal, Optional

from app.agent.graph import build_graph
from app.agent.state import new_state
from app.nodes.planner import summary
from app.nodes.profiler import profile_to_payload, public_profile
from app.nodes.profiler import run as profiler_run
from app.tools import llm
import uuid

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
    """Postgres 에 붙었는지. /health 에서 노출하면 디버깅이 쉽다."""
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
def _response(state: dict, reply: str | None = None,
              ui_type: str | None = None, ui_payload: dict | None = None) -> dict:
    return {
        "schema_version": "1",
        "reply": reply if reply is not None else (state.get("reply") or ""),
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
    """session_id 를 주지 않으면 새 세션을 만든다."""
    sid = session_id or f"s-{uuid.uuid4().hex[:10]}"
    state = _graph().invoke(_patch(sid, {"locale": locale}), _cfg(sid))
    return _response(state)


def extract(session_id: str, image: bytes, doc_type: DocType,
            ext: str = "jpg") -> dict:
    """신분증 → 프로필 갱신 → Task Graph 재계산."""
    holder: dict = {"profile": {}, "confidence": {}}
    holder, payload = profiler_run(holder, image, doc_type, ext=ext)

    state = _graph().invoke(_patch(session_id, {
        "profile": holder["profile"],
        "confidence": holder["confidence"],
        "raw_texts": holder.get("raw_texts", []),
        "dropped": holder.get("dropped", []),
    }), _cfg(session_id))

    # 누적된 전체 프로필 기준으로 확인 카드를 다시 만든다
    payload = profile_to_payload(state.get("profile", {}),
                                 state.get("confidence", {}), doc_type)

    low = [f["key"] for f in payload["fields"] if f["confidence"] < 0.90]
    head = ("신분증을 확인했습니다." if not low else
            f"신분증을 확인했습니다. {len(low)}개 항목은 확인이 필요합니다.")
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
    "entry_date":    ("Date of entry into Korea (YYYY-MM-DD)", None),
    "org_name":      ("Name of the school or organization", None),
    "phone_kr":      ("Phone number in Korea", None),
    "purpose":       ("Purpose of the bank account",
                      {"living_expense": 1, "tuition": 1, "salary": 1, "remittance": 1}),
    "income_source": ("Source of funds",
                      {"scholarship": 1, "family_support": 1, "part_time": 1, "savings": 1}),
}


def send_message(session_id: str, message: str) -> dict:
    """대화 입력.

    슬롯 필링 중이면 LLM 이 자유 발화에서 값을 뽑는다.
    추출 실패 시 프로필을 건드리지 않고 되묻는다 — 쓰레기 값이 서류로 가지 않는다.
    """
    snap = _graph().get_state(_cfg(session_id)).values if _seen(session_id) else {}
    asked = snap.get("asked_field")

    extra: dict[str, Any] = {"messages": [{"role": "user", "content": message}]}

    if asked:
        value, failed = message.strip(), None

        if llm.available():
            label, enum = _FIELD_META.get(asked, (asked, None))
            parsed = llm.parse_answer(asked, label=label, message=message,
                                      enum=enum, locale=snap.get("locale", "ko"))
            if parsed is None:
                pass                                  # LLM 실패 → 원문 사용
            elif parsed.get("ok") and parsed.get("value"):
                value = parsed["value"]
            else:
                failed = parsed.get("reason") or "값을 알아듣지 못했습니다."
                failed = failed.strip()

        if failed:
            # 같은 필드를 다시 묻는다. asked_field 를 유지한다.
            state = _graph().get_state(_cfg(session_id)).values
            return _response(state, failed, "question",
                             state.get("ui_payload") or {})

        extra["profile"] = {asked: value}
        extra["asked_field"] = None

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


def approve(session_id: str, action_id: str, approved: bool = True) -> dict:
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