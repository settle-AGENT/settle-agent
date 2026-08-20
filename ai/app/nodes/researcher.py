"""Researcher — 조회 도구를 모델이 스스로 골라 답을 만든다.

이 파일이 이 시스템에서 LLM 이 자율적으로 도는 유일한 곳이다. 자유는
"무엇을 몇 번 찾아볼지" 까지고, "가능한가" 는 여전히 룰이 정한다.

  설계 규칙 — 도구는 결론을 돌려준다. 판단 재료를 돌려주지 않는다.

    ✗ get_visa_rules()  → visa_matrix.yaml 원문
                          모델이 "D-2 가 계좌 되나" 를 추론하게 된다
    ✓ get_tasks()       → status="locked", blocked_by=[...]
                          planner 가 이미 낸 결론을 전달만 한다

  이 규칙을 어기는 도구를 하나라도 추가하면 체류자격 판정이 모델로 넘어간다.

실행 도구는 여기 없다. 되돌릴 수 없는 행동은 approval_gate 를 거치고,
잠긴 과제는 start_action / preview_action 진입점에서 한 번 더 막힌다.
모델은 틀린 말을 할 수는 있어도 틀린 행동은 하지 못한다.
"""
from __future__ import annotations

import json
import os

from anthropic import beta_tool

from app.nodes import qa
from app.rules.loader import actions_for, evidence_labels
from app.tools import llm

# 루프가 폭주하지 않도록 왕복 횟수를 묶는다. 조회 3~4 번이면 충분한 질문들이다.
MAX_ITERATIONS = int(os.getenv("RESEARCH_MAX_ITERATIONS", "6"))
MAX_TOKENS = int(os.getenv("RESEARCH_MAX_TOKENS", "4096"))

_SYSTEM = """You are a settlement assistant for foreign residents in Korea.

Answer the user's question using the tools. Never answer from memory —
immigration rules change and a wrong answer can cost someone their visa.

How to work:
- Call get_tasks first when the question touches what the user should do,
  what is blocked, or when something is due. It returns the already-decided
  status for THIS user. Treat it as authoritative.
- Call check_requirements for what to bring and where to submit.
- Call search_law for what a statute or the immigration manual actually says.
  Search in Korean terms when you can; the corpus is Korean.
- Call tools more than once if the first result does not answer the question.

Hard rules:
- Never say a task is possible when get_tasks reports it locked. Say what is
  blocking it and what to do first.
- Never invent a deadline, a fee, a document name, or an office. If the tools
  do not say it, say you could not confirm it and point to 1345 (the
  immigration call center) or the bank counter.
- Do not compute eligibility yourself. The tools already did.
- Write in the user's language.

Format — this is a chat bubble on a phone, not a document:
- Plain text only. No markdown, no **bold**, no bullet characters, no emoji.
- Three or four sentences. If you must list documents, put them on one line
  separated by commas.
- Lead with the answer, then the one thing they should do next.
"""


def available() -> bool:
    return llm.available() and qa.available()


# ──────────────────────────────────────────────────────────
# 도구
# ──────────────────────────────────────────────────────────
def _build_tools(profile: dict, tasks: list[dict], trace: list[dict]):
    """세션 문맥을 클로저로 묶어 도구를 만든다.

    trace 는 모델이 무엇을 몇 번 조회했는지 기록한다 — 루프가 실제로
    돌았는지 확인하는 유일한 근거다.
    """
    visa = profile.get("visa_type")

    @beta_tool
    def get_tasks() -> str:
        """List this user's settlement tasks with their current status.

        Returns each task's id, label, status (available / locked / in_progress
        / done), what is blocking it, the deadline and days left, the office to
        submit to, and the documents to bring. The status is already decided
        from the user's visa — do not second-guess it.
        """
        trace.append({"tool": "get_tasks", "input": {}})
        return json.dumps([{
            "id": t["id"],
            "label": t["label"],
            "status": t["status"],
            "blocked_by": t.get("blocked_by") or [],
            "deadline": t.get("deadline"),
            "days_left": t.get("d_day"),
            "office": t.get("agency"),
            "documents": t.get("required_docs") or [],
            "note": t.get("note"),
        } for t in tasks], ensure_ascii=False)

    @beta_tool
    def check_requirements(action_id: str) -> str:
        """Look up what one task requires.

        Args:
            action_id: A task id from get_tasks, e.g. alien_registration.
        """
        trace.append({"tool": "check_requirements",
                      "input": {"action_id": action_id}})
        spec = actions_for(visa).get(action_id)
        if not spec:
            return json.dumps({"error": "unknown task for this visa",
                               "action_id": action_id}, ensure_ascii=False)
        return json.dumps({
            "action_id": action_id,
            "allowed": spec.get("allowed"),
            "prerequisites": spec.get("prereq") or [],
            "documents": spec.get("required_docs") or [],
            "deadline_rule": spec.get("deadline"),
            "legal_basis": evidence_labels(spec.get("evidence") or []),
            "note": spec.get("note_ko") or spec.get("condition_ko"),
        }, ensure_ascii=False)

    @beta_tool
    def search_law(query: str) -> str:
        """Search Korean immigration law and the official residence manual.

        Args:
            query: What to look up. Korean terms work best, e.g.
                체류기간 연장허가 제출서류.
        """
        trace.append({"tool": "search_law", "input": {"query": query}})
        hits = qa.search(query, visa=visa)
        if not hits:
            return json.dumps({"results": []}, ensure_ascii=False)
        return json.dumps({"results": [{
            "cite": h["cite"],
            "text": h["text"][:900],
        } for h in hits]}, ensure_ascii=False)

    return [get_tasks, check_requirements, search_law]


# ──────────────────────────────────────────────────────────
# 루프
# ──────────────────────────────────────────────────────────
def answer(question: str, *, profile: dict, tasks: list[dict],
           history: list[dict] | None = None,
           locale: str = "en") -> dict | None:
    """returns {"reply": str, "cites": [str], "trace": [...]} 또는 None"""
    client = llm.client()
    if client is None:
        return None

    trace: list[dict] = []
    tools = _build_tools(profile, tasks, trace)

    situation = {
        "visa_type": profile.get("visa_type"),
        "nationality": profile.get("nationality"),
        "has_arc": bool(profile.get("arc_no")),
        "stay_expiry": profile.get("stay_expiry"),
        "organization": profile.get("org_name"),
    }
    opening = (f"User situation: {json.dumps(situation, ensure_ascii=False)}\n"
               f"Answer in: {llm.LANG.get(locale, locale)}\n\n"
               f"Question: {question}")

    messages = [{"role": "user", "content": m["content"]}
                if m.get("role") == "user" else
                {"role": "assistant", "content": m["content"]}
                for m in (history or [])[-4:]]
    messages.append({"role": "user", "content": opening})

    try:
        runner = client.beta.messages.tool_runner(
            model=llm.MODEL,
            max_tokens=MAX_TOKENS,
            max_iterations=MAX_ITERATIONS,
            system=_SYSTEM,
            tools=tools,
            messages=messages,
        )
        final = None
        for message in runner:
            final = message
    except Exception as exc:                                  # noqa: BLE001
        # 루프가 실패해도 대화가 끊기지 않게 한다. 호출부가 기존 RAG 로 내려간다.
        print(f"[researcher] tool loop 실패, RAG 로 폴백: {exc!r}")
        return None

    if final is None:
        return None

    reply = "".join(b.text for b in final.content if b.type == "text").strip()
    if not reply:
        return None

    # 인용은 모델이 아니라 실제로 조회된 결과에서 뽑는다 — 지어낸 근거를 막는다.
    cites: list[str] = []
    for step in trace:
        if step["tool"] != "search_law":
            continue
        for h in qa.search(step["input"]["query"], visa=profile.get("visa_type")):
            if h["cite"] in reply or h["cite"] not in cites:
                cites.append(h["cite"])
    return {"reply": reply, "cites": cites[:3], "trace": trace}
