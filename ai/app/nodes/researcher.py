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
from app.nodes.doc_builder import load_mapping
from app.rules.loader import actions_for, evidence_labels
from app.tools import llm
from app.tools import progress

# 루프가 폭주하지 않도록 왕복 횟수를 묶는다. 조회 3~4 번이면 충분한 질문들이다.
MAX_ITERATIONS = int(os.getenv("RESEARCH_MAX_ITERATIONS", "6"))
MAX_TOKENS = int(os.getenv("RESEARCH_MAX_TOKENS", "4096"))

_SYSTEM = """You are the assistant inside a settlement app for foreign
residents in Korea. You are part of the app, not a separate chatbot.

What this app does for the user — never deny any of it:
- It fills in the official application forms for them. get_tasks tells you
  which form each task produces in prepares_form. If it is not null, the app
  writes that form from the profile it already has.
- It tracks their tasks, deadlines and what is still blocked.
- It looks up immigration law and the official residence manual.

So when the user asks "can you do it for me", "대신 작성해줘", "신청서 만들어줘",
or asks how to fill in a form the app produces: the answer is YES. Say the app
will prepare it, name the form, and tell them to say so and you will start.
Never say you cannot write documents. Never call yourself a chatbot that only
gives information. Never send them to download a blank form when prepares_form
shows the app makes it.

What the app does NOT do: it does not submit anything to a government office or
a bank, and it does not open the account. The user still goes in person. Be
straight about that line.

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
- If get_tasks returns error "no_profile", stop there. Tell them you need
  their residence card first and that everything — deadlines, what is blocked,
  which forms you can fill in — depends on it. Do not answer the personal part
  of their question from general knowledge, and do not cite another visa's
  manual pages at them. A general legal question is still fine to answer.

Hard rules:
- ALWAYS END WITH THE NEXT STEP. You are not a reference desk. If get_tasks
  shows any task the user can start right now, your last sentence offers to
  start it — and you call offer_to_start for it in the same turn. Even when they
  only asked for information. Answer first, then offer.
  The only time you do not offer is when nothing is startable (no profile, or
  everything is done or blocked with nothing available).
- THE OFFER RULE. If your last sentence asks the user whether to start, prepare,
  or write something — "시작할까요?", "준비해드릴까요?", "작성할까요?", "Shall I
  start?" — you MUST call offer_to_start for that task in the same turn. No
  exception. Without it the user's "네" attaches to nothing and the whole
  conversation dead-ends. Either call the tool, or do not end with that question.
  Offer exactly one task, and never a locked one — if offer_to_start comes back
  locked, offer the task that is blocking it instead.
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
def _form_title(visa: str | None, action_id: str, locale: str) -> str | None:
    """이 과제에서 앱이 대신 작성해 주는 서식 이름. 없으면 None.

    모델이 "서류는 못 만들어 드립니다" 라고 말하지 않게 하려면, 만들 수 있다는
    사실이 프롬프트가 아니라 도구 결과로 들어와야 한다.
    """
    form = (actions_for(visa).get(action_id) or {}).get("form")
    if not form:
        return None
    try:
        meta = load_mapping(form)
    except FileNotFoundError:
        return None
    return meta.get(f"title_{locale}") or meta.get("title_ko")


def _build_tools(profile: dict, tasks: list[dict], trace: list[dict],
                 offer: dict, locale: str = "en", session_id: str = ""):
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
        progress.emit(session_id, "tool_tasks", "현재 할 일과 완료 상태를 조회하고 있어요")
        trace.append({"tool": "get_tasks", "input": {}})
        if not visa:
            # 신분증을 아직 안 올렸다. 이 사람의 체류자격·기한·잠김을 알 방법이
            # 없으므로, 아는 척하지 말고 등록증부터 받아야 한다.
            return json.dumps({
                "error": "no_profile",
                "hint": "The user has not uploaded their residence card yet. "
                        "You cannot know their visa, their deadlines, what is "
                        "blocked, or which forms this app can prepare for them. "
                        "Do not guess and do not answer as if you knew. Ask them "
                        "to photograph their residence card first.",
            }, ensure_ascii=False)
        return json.dumps([{
            "id": t["id"],
            "label": t["label"],
            "status": t["status"],
            "blocked_by": t.get("blocked_by") or [],
            "deadline": t.get("deadline"),
            "days_left": t.get("d_day"),
            "office": t.get("agency"),
            "documents": t.get("required_docs") or [],
            "prepares_form": _form_title(visa, t["id"], locale),
            "note": t.get("note"),
        } for t in tasks], ensure_ascii=False)

    @beta_tool
    def check_requirements(action_id: str) -> str:
        """Look up what one task requires.

        Args:
            action_id: A task id from get_tasks, e.g. alien_registration.
        """
        action_label = next((t.get("label") for t in tasks if t.get("id") == action_id), action_id)
        progress.emit(session_id, "tool_requirements", f"{action_label} 요건과 준비물을 확인하고 있어요")
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
            "prepares_form": _form_title(visa, action_id, locale),
            "note": spec.get("note_ko") or spec.get("condition_ko"),
        }, ensure_ascii=False)

    @beta_tool
    def search_law(query: str) -> str:
        """Search Korean immigration law and the official residence manual.

        Args:
            query: What to look up. Korean terms work best, e.g.
                체류기간 연장허가 제출서류.
        """
        safe_query = " ".join(query.strip().split())[:32]
        progress.emit(session_id, "tool_law", f"‘{safe_query}’ 법령·지침을 검색하고 있어요")
        trace.append({"tool": "search_law", "input": {"query": query}})
        hits = qa.search(query, visa=visa)
        if not hits:
            return json.dumps({"results": []}, ensure_ascii=False)
        return json.dumps({"results": [{
            "cite": h["cite"],
            "text": h["text"][:900],
        } for h in hits]}, ensure_ascii=False)

    @beta_tool
    def offer_to_start(action_id: str) -> str:
        """Offer to start a task, so a plain "yes" from the user works next turn.

        Call this whenever you tell the user the app can prepare something and
        they only have to say so. Without it their "네" has nothing to attach to
        and falls through as a new question.

        This does not start or submit anything. It only records what you just
        offered.

        Args:
            action_id: A task id from get_tasks. Must not be locked or done.
        """
        action_label = next((t.get("label") for t in tasks if t.get("id") == action_id), action_id)
        progress.emit(session_id, "tool_offer", f"{action_label} 시작 선택지를 준비하고 있어요")
        trace.append({"tool": "offer_to_start", "input": {"action_id": action_id}})
        task = next((t for t in tasks if t["id"] == action_id), None)
        if task is None:
            return json.dumps({"ok": False, "reason": "unknown task"},
                              ensure_ascii=False)
        if task["status"] == "done":
            return json.dumps({"ok": False, "reason": "already done"},
                              ensure_ascii=False)
        if task["status"] == "locked":
            # 잠긴 것을 권하면 사용자가 승낙해도 409 가 난다. 막고 있는 것을 알려준다.
            return json.dumps({
                "ok": False, "reason": "locked",
                "blocked_by": task.get("blocked_by") or [],
                "hint": "Offer the blocking task instead.",
            }, ensure_ascii=False)
        offer["value"] = {"kind": "start_action", "action_id": action_id,
                          "label": task["label"]}
        return json.dumps({"ok": True, "offered": task["label"]},
                          ensure_ascii=False)

    return [get_tasks, check_requirements, search_law, offer_to_start]


# ──────────────────────────────────────────────────────────
# 루프
# ──────────────────────────────────────────────────────────
def answer(question: str, *, profile: dict, tasks: list[dict],
           history: list[dict] | None = None,
           locale: str = "en", session_id: str = "") -> dict | None:
    """returns {"reply", "cites", "trace", "offer"} 또는 None

    offer 는 모델이 offer_to_start 를 불렀을 때만 채워진다. 호출부가 이것을
    state.pending_offer 로 넣어 두어야 다음 턴의 "ㅇㅇ" 이 해석된다.
    """
    client = llm.client()
    if client is None:
        return None

    trace: list[dict] = []
    texts: list[str] = []
    offer: dict = {"value": None}
    tools = _build_tools(profile, tasks, trace, offer, locale, session_id)

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
        # 답변 텍스트가 마지막 턴에 있으리라는 보장이 없다. 모델은 도구 호출과
        # 같은 턴에 답을 쓰고, 다음 턴을 빈 내용으로 끝내는 일이 흔하다.
        # 턴마다 텍스트를 모아 마지막으로 비어 있지 않은 것을 쓴다.
        final = None
        for message in runner:
            final = message
            said = "".join(b.text for b in message.content
                           if b.type == "text").strip()
            if said:
                texts.append(said)
    except Exception as exc:                                  # noqa: BLE001
        # 루프가 실패해도 대화가 끊기지 않게 한다. 호출부가 기존 RAG 로 내려간다.
        print(f"[researcher] tool loop 실패, RAG 로 폴백: {exc!r}")
        return None

    if final is None or not texts:
        return None

    reply = texts[-1]

    # 인용은 모델이 아니라 실제로 조회된 결과에서 뽑는다 — 지어낸 근거를 막는다.
    cites: list[str] = []
    for step in trace:
        if step["tool"] != "search_law":
            continue
        for h in qa.search(step["input"]["query"], visa=profile.get("visa_type")):
            if h["cite"] in reply or h["cite"] not in cites:
                cites.append(h["cite"])
    return {"reply": reply, "cites": cites[:3], "trace": trace,
            "offer": offer["value"]}
