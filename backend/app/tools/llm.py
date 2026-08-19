"""LLM 래퍼 — Anthropic Claude.

설계 원칙
  - LLM 은 **문장을 만들고, 답변에서 값을 뽑는 일**만 한다.
  - 무엇을 물을지, 가능한지 여부는 룰 엔진이 이미 정해두고 넘긴다.
  - 실패하면 예외를 던지지 않고 폴백 값을 돌려준다. 대화가 끊기면 안 된다.
  - 출력은 항상 JSON 스키마로 강제해 자유 텍스트가 시스템에 유입되지 않게 한다.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from functools import lru_cache
from typing import Any

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
MAX_TOKENS = 512

LANG = {"ko": "Korean", "en": "English", "vi": "Vietnamese"}


@lru_cache(maxsize=1)
def _client():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        from anthropic import Anthropic
        return Anthropic(api_key=key)
    except Exception as exc:                                  # noqa: BLE001
        print(f"[llm] Anthropic 클라이언트 생성 실패: {exc!r}")
        return None


def available() -> bool:
    return _client() is not None


def _call(system: str, user: str, *, tool: dict | None = None,
          max_tokens: int = MAX_TOKENS) -> Any:
    """tool 을 주면 구조화 출력(dict), 없으면 텍스트(str)."""
    c = _client()
    if c is None:
        return None

    kwargs: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if tool:
        kwargs["tools"] = [tool]
        kwargs["tool_choice"] = {"type": "tool", "name": tool["name"]}

    try:
        res = c.messages.create(**kwargs)
    except Exception as exc:                                  # noqa: BLE001
        print(f"[llm] 호출 실패: {exc!r}")
        return None

    if tool:
        for block in res.content:
            if block.type == "tool_use":
                return block.input
        return None

    return "".join(b.text for b in res.content if b.type == "text").strip()


# ══════════════════════════════════════════════════════════
# 1. 질문 문장 생성 — 무엇을 물을지는 코드가 이미 정했다
# ══════════════════════════════════════════════════════════
_ASK_SYSTEM = """You write ONE short question for a form-filling assistant used by
foreign residents in Korea. They are not fluent in Korean and are stressed by paperwork.

Rules:
- Ask ONLY for the given field. Never ask for anything else.
- One sentence. Plain, warm, concrete. No greetings, no apologies.
- Never invent requirements, deadlines, or legal claims.
- Reply in the requested language."""


def ask_field(field: str, *, label: str, locale: str = "en",
              context: dict | None = None, remaining: int = 1) -> dict | None:
    """부족한 필드 하나를 묻는 문장을 만든다.

    returns {"question": str, "hint": str|None} 또는 None(폴백은 호출자가)
    """
    ctx = {k: v for k, v in (context or {}).items()
           if k in ("visa_type", "name_en", "org_name", "nationality")}

    return _call(
        _ASK_SYSTEM,
        f"Field to ask: {field}\n"
        f"Meaning: {label}\n"
        f"User context: {json.dumps(ctx, ensure_ascii=False)}\n"
        f"Questions remaining after this: {remaining - 1}\n"
        f"Language: {locale}",
        tool={
            "name": "write_question",
            "description": "Return the question to show the user.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string",
                                 "description": "One short question."},
                    "hint": {"type": ["string", "null"],
                             "description": "Optional one-line hint, or null."},
                },
                "required": ["question"],
            },
        },
    )


# ══════════════════════════════════════════════════════════
# 2. 답변에서 값 추출 — 자유 발화를 필드 값으로
# ══════════════════════════════════════════════════════════
_PARSE_SYSTEM = """You extract ONE field value from a user's reply in a form-filling flow.

Rules:
- Extract only what the user actually said. Never invent facts.
- Dates must be YYYY-MM-DD. Resolve relative expressions ("last year", "지난달",
  "작년 8월 15일") against the given today's date. That is resolution, not guessing.
- If the reply is genuinely ambiguous or does not answer the field,
  set ok=false and leave value empty.
- Keep the user's own spelling for names and institutions.
- Normalize Korean phone numbers to 010-0000-0000 form when possible.

The "reason" field is shown directly to the user, so:
- ONE short sentence, in the requested language.
- Say what you need, not what you inferred. Never explain your reasoning.
- Good: "정확한 날짜를 알려주세요. 예: 2026-08-15"
- Bad:  "The user said last week but did not specify which day..."."""


def parse_answer(field: str, *, label: str, message: str,
                 enum: dict | None = None, today: str | None = None,
                 locale: str = "ko") -> dict | None:
    """returns {"ok": bool, "value": str, "reason": str|None}"""
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean",
                   "description": "true only if a valid value was found"},
            "value": {"type": "string"},
            "reason": {"type": ["string", "null"],
                       "description": "One short sentence shown to the user, "
                                      "asking for what is needed. Only when ok=false."},
        },
        "required": ["ok", "value"],
    }
    if enum:
        schema["properties"]["value"]["enum"] = list(enum)

    allowed = f"\nAllowed values: {list(enum)}" if enum else ""
    return _call(
        _PARSE_SYSTEM,
        f"Today is {today or date.today().isoformat()}.\n"
        f"Language for 'reason': {LANG.get(locale, locale)}\n"
        f"Field: {field}\nMeaning: {label}{allowed}\n\nUser reply: {message}",
        tool={
            "name": "extract_value",
            "description": "Return the extracted field value.",
            "input_schema": schema,
        },
    )


# ══════════════════════════════════════════════════════════
# 3. 설명 — 룰이 내린 판정을 사람 말로
# ══════════════════════════════════════════════════════════
_EXPLAIN_SYSTEM = """You explain a decision that was ALREADY made by a rule engine,
to a foreign resident in Korea.

Absolute rules:
- Never change the verdict. Never add requirements, deadlines, or exceptions.
- Never cite a law that is not in the provided evidence list.
- If evidence is empty, do not mention any law.
- 2-3 short sentences. Warm, concrete, no filler.
- If next_action_agency / next_action_documents are given, say WHERE to submit
  and WHAT to bring. Concrete beats vague.
- End with the call_to_action if one is provided.
- Plain sentences only. No markdown, no bold, no bullet points.
- Reply in the requested language."""


def explain(verdict: dict, *, locale: str = "en") -> str | None:
    """verdict 예:
    {"question": "...", "allowed": "conditional",
     "condition": "체류자격외활동허가 필요",
     "blocked_by": ["외국인등록"], "evidence": ["출입국관리법 제20조"],
     "next_action_label": "외국인등록"}
    """
    return _call(
        _EXPLAIN_SYSTEM,
        f"Decision from rule engine:\n{json.dumps(verdict, ensure_ascii=False, indent=2)}\n"
        f"Language: {locale}",
        max_tokens=300,
    )


# ══════════════════════════════════════════════════════════
# 4. 의도 분류 — 라우팅
# ══════════════════════════════════════════════════════════
_ROUTE_SYSTEM = """Classify the user's message in a Korean settlement-assistant app.

- answer   : replying to the field the assistant just asked
- question : asking whether something is possible / what is needed
- action   : asking to start or do a task
- other    : greeting, thanks, unrelated"""


def classify(message: str, *, asked_field: str | None = None,
             actions: list[str] | None = None) -> dict | None:
    """returns {"intent": str, "action_id": str|None, "topic": str|None}"""
    return _call(
        _ROUTE_SYSTEM,
        f"Assistant just asked for: {asked_field or '(nothing)'}\n"
        f"Available actions: {actions or []}\n\nUser message: {message}",
        tool={
            "name": "classify_intent",
            "description": "Classify the user's message.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string",
                               "enum": ["answer", "question", "action", "other"]},
                    "action_id": {"type": ["string", "null"],
                                  "description": "action id if intent=action"},
                    "topic": {"type": ["string", "null"],
                              "description": "short topic if intent=question"},
                },
                "required": ["intent"],
            },
        },
    )


# ══════════════════════════════════════════════════════════
# 5. 번역 — 이미 확정된 문구를 옮기기만
# ══════════════════════════════════════════════════════════
_TR_SYSTEM = """Translate the text. Keep it literal.
Do not add, remove, soften, or explain anything.
Keep proper nouns, law names, numbers, and dates unchanged."""


def translate(text: str, locale: str) -> str:
    if not text or locale == "ko" or not available():
        return text
    out = _call(_TR_SYSTEM, f"Target language: {LANG.get(locale, locale)}\n\n{text}",
                max_tokens=400)
    return out or text

# ══════════════════════════════════════════════════════════
# 6. 법령 질의응답 — 주어진 조문 안에서만 답한다
# ══════════════════════════════════════════════════════════
_QA_SYSTEM = """You help foreign residents in Korea with immigration and banking
procedures. You are mid-conversation with one specific person.

Two kinds of input, with different authority:
1. STATUTE EXCERPTS — the only source for what the law says. Never state a legal
   rule, article number, deadline or penalty that is not in them. If they do not
   cover the question, set covered=false and write nothing.
2. THIS USER'S CASE — visa type, deadlines, which office, which documents to bring.
   This comes from our own rule engine and is authoritative. Use it. Answer for
   THIS person, not in general. "It depends on your visa" is a failure when their
   visa is right there in front of you.

If their case data alone answers the question (e.g. what to bring, where to go,
by when), answer from it and set covered=true even if the excerpts add nothing.

Style:
- Plain sentences. No markdown, no bullets, no bold. 2-4 sentences.
- The user's language.
- Resolve references to earlier turns using the conversation history.
- Legal information, never legal advice, never a guarantee. For a ruling on their
  individual case, point them to the Immigration Contact Center (1345) or their bank.
- Put in `cited` only the excerpt ids you actually used. Empty list is fine when you
  answered purely from their case data."""


def answer_question(question: str, *, passages: list[dict], situation: dict,
                    history: list[dict] | None = None,
                    locale: str = "en") -> dict | None:
    """returns {"answer": str, "cited": [id], "covered": bool}"""
    body = "\n\n".join(f"[{p['id']}] {p['cite']}\n{p['text']}" for p in passages) \
        or "(none retrieved)"
    turns = "\n".join(f"{m.get('role')}: {m.get('content')}"
                       for m in (history or [])[-6:]) or "(start of conversation)"
    return _call(
        _QA_SYSTEM,
        f"Conversation so far:\n{turns}\n\n"
        f"Statute excerpts:\n{body}\n\n"
        f"This user's case: {json.dumps(situation, ensure_ascii=False)}\n"
        f"Language: {locale}\n\n"
        f"Their question: {question}",
        tool={
            "name": "give_answer",
            "description": "Answer this person's question.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "covered": {"type": "boolean"},
                    "answer": {"type": "string"},
                    "cited": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["covered", "answer", "cited"],
            },
        },
        max_tokens=500,
    )
