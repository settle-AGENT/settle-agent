"""법령·안내매뉴얼 질의응답 — 하이브리드 검색 후 LLM이 검색된 근거 안에서만 답한다.

코퍼스는 둘이다.
  rules/corpus.json  법령 조문 — 무엇이 규정인지
  rules/manual.json  출입국 안내매뉴얼 — 체류자격별로 무엇을 어떻게 내는지

벡터(pgvector)가 의미를, BM25가 조문 번호·고유 표현을 잡는다.
두 순위를 RRF로 합친 뒤, 사용자의 체류자격에 맞는 매뉴얼 조각을 끌어올린다.
DB나 모델이 없으면 BM25 단독으로 동작한다.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from app.tools import embed, llm

_RULES = Path(__file__).resolve().parents[2] / "rules"
CORPUS = _RULES / "corpus.json"
MANUAL = _RULES / "manual.json"

ALIAS = {
    "이사": "체류지 변경신고", "전입": "체류지 변경신고",
    "알바": "시간제취업 체류자격 외 활동", "아르바이트": "시간제취업 체류자격 외 활동",
    "취업": "체류자격 외 활동 근무처", "계좌": "금융거래 실명 예금",
    "통장": "금융거래 실명 예금", "등록증": "외국인등록증", "비자": "체류자격",
    "연장": "체류기간 연장허가", "송금": "외국환 지급", "과태료": "과태료 벌칙",
    "신분증": "실지명의 실명확인", "유학생": "외국인유학생",
    "서류": "제출서류", "준비물": "제출서류", "수수료": "심사수수료",
    "학교": "학교 변경 재학증명서", "휴학": "체류기간 연장 학업 중단",
    "졸업": "유학활동 종료 체류기간", "이직": "근무처의 변경 추가",
    "재입국": "재입국허가", "결핵": "결핵진단서",
}

_STRIP = re.compile(r"[^가-힣A-Za-z0-9]")
_HANGUL = re.compile(r"[가-힣]")
_RRF_K = 60          # Reciprocal Rank Fusion 상수
_POOL = 12           # 각 검색기가 내놓는 후보 수
_TOP = 5             # LLM에 넘길 근거 수

_MATCH_VISA = 1.6    # 사용자 자격의 매뉴얼 조각을 끌어올린다
_OTHER_VISA = 0.45   # 다른 자격 전용 조각은 눌러둔다 — 오답의 주된 원인


# ────────────────────────────────────────────── 코퍼스 · BM25
def _grams(s: str) -> list[str]:
    s = _STRIP.sub("", s)
    return [s[i:i + 2] for i in range(len(s) - 1)] or ([s] if s else [])


@lru_cache(maxsize=1)
def _index():
    docs: list[dict] = []
    for path in (CORPUS, MANUAL):
        if path.exists():
            docs.extend(json.loads(path.read_text(encoding="utf-8")))
    if not docs:
        return [], [], [], 1.0, Counter(), 0
    toks = [Counter(_grams(d["heading"] * 3 + d["text"])) for d in docs]
    lens = [sum(c.values()) for c in toks]
    avg = (sum(lens) / len(lens)) if lens else 1.0
    df = Counter()
    for c in toks:
        df.update(c.keys())
    return docs, toks, lens, avg, df, len(docs)


def available() -> bool:
    return _index()[5] > 0


def _korean(q: str) -> str:
    """영문 질문은 한국어 검색어로 옮긴 뒤 검색한다.

    코퍼스가 전부 한국어라 그냥 두면 양쪽 다 무너진다 — BM25는 한글 음절
    바이그램이라 영문에서 신호를 못 내고, 벡터도 한국어 조문과는 거리가 멀다.
    번역이 안 되면(LLM 미설정 등) 원문으로 검색한다. 다국어 임베딩이라
    아주 못 찾지는 않는다.
    """
    if _HANGUL.search(q) or not llm.available():
        return q
    return llm.translate_query(q) or q


def _expand(q: str, visa: str | None = None) -> str:
    """줄임말을 법령 용어로 펴고, 아는 체류자격은 질의에 실어 보낸다."""
    out = q + " " + " ".join(v for k, v in ALIAS.items() if k in q)
    if visa:
        out += " " + visa + " " + visa.replace("-", "")
    return out


def _bm25(query: str, k: int, k1: float = 1.4, b: float = 0.75) -> list[str]:
    docs, toks, lens, avg, df, n = _index()
    if not n:
        return []
    qg = Counter(_grams(query))
    scored = []
    for i, c in enumerate(toks):
        s = 0.0
        for g in qg:
            f = c.get(g, 0)
            if not f:
                continue
            idf = math.log(1 + (n - df[g] + 0.5) / (df[g] + 0.5))
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * lens[i] / avg))
        if s > 0:
            scored.append((s, docs[i]["id"]))
    scored.sort(reverse=True)
    return [i for _, i in scored[:k]]


# ────────────────────────────────────────────── 벡터
def _vector(query: str, k: int) -> list[str]:
    url = os.getenv("DATABASE_URL")
    if not url:
        return []
    try:
        import psycopg
        vec = embed.to_pg(embed.encode([query], is_query=True)[0])
        with psycopg.connect(url) as conn:
            rows = conn.execute(
                "SELECT id FROM rag.chunk ORDER BY embedding <=> %s::vector LIMIT %s",
                (vec, k)).fetchall()
        return [r[0] for r in rows]
    except Exception as exc:                       # noqa: BLE001
        print(f"[qa] 벡터 검색 건너뜀: {exc!r}")
        return []

# ────────────────────────────────────────────── 융합
def _visa_weight(doc: dict, visa: str | None) -> float:
    """매뉴얼은 체류자격별로 쓰여 있다. 남의 자격 설명은 그 사람에겐 오답이다."""
    tags = doc.get("visa") or []
    if not visa or not tags:                       # 법령·공통사항은 누구에게나 해당
        return 1.0
    base = visa.split("-")[:2]                     # D-2-1 소지자에게 D-2 장은 맞는 설명
    for t in tags:
        if t == visa or t.split("-")[:2] == base:
            return _MATCH_VISA
    return _OTHER_VISA


def search(query: str, k: int = _TOP, *, visa: str | None = None) -> list[dict]:
    docs = _index()[0]
    if not docs:
        return []
    by_id = {d["id"]: d for d in docs}

    expanded = _expand(_korean(query), visa)
    ranks = defaultdict(float)
    used = {"vector": _vector(expanded, _POOL), "bm25": _bm25(expanded, _POOL)}
    for names in used.values():
        for pos, doc_id in enumerate(names):
            ranks[doc_id] += 1.0 / (_RRF_K + pos + 1)

    if not ranks:
        return []

    scored = {i: s * _visa_weight(by_id[i], visa) for i, s in ranks.items()}
    top = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:k]
    out = []
    for doc_id, score in top:
        d = dict(by_id[doc_id])
        d["score"] = round(score, 4)
        d["found_by"] = [name for name, ids in used.items() if doc_id in ids]
        out.append(d)
    return out


# ────────────────────────────────────────────── 답변
_ANAPHORA = re.compile(
    r"\b(it|that|there|they|them|those|this|earlier|mentioned|above)\b"
    r"|거기|그곳|그거|그건|아까|말한|위에서|앞서", re.I)


def _retrieval_query(question: str, history: list[dict] | None) -> str:
    """지시어가 섞인 후속 질문은 직전 발화를 붙여야 검색이 된다."""
    if not history or not _ANAPHORA.search(question):
        return question
    prev = next((m.get("content", "") for m in reversed(history[:-1])
                 if m.get("role") == "user"), "")
    return f"{prev} {question}".strip()


def answer(question: str, *, profile: dict, tasks: list[dict],
           history: list[dict] | None = None,
           locale: str = "en") -> dict | None:
    """returns {"reply": str, "cites": [str]} 또는 None(답변 불가)"""
    if not llm.available():
        return None

    hits = search(_retrieval_query(question, history),
                  visa=profile.get("visa_type"))

    situation = {
        "visa_type": profile.get("visa_type"),
        "nationality": profile.get("nationality"),
        "has_arc": bool(profile.get("arc_no")),
        "stay_expiry": profile.get("stay_expiry"),
        "organization": profile.get("org_name"),
        "tasks": [{
            "label": t["label"], "status": t["status"],
            "office": t.get("agency"),
            "documents_to_bring": t.get("required_docs") or [],
            "deadline": t.get("deadline"), "days_left": t.get("d_day"),
            "note": t.get("note"),
            "blocked_by": t.get("blocked_by") or [],
        } for t in tasks],
    }

    got = llm.answer_question(question, passages=hits, situation=situation,
                              history=history, locale=locale)
    if not got or not got.get("covered") or not got.get("answer"):
        return None

    by_id = {h["id"]: h["cite"] for h in hits}
    cites = [by_id[c] for c in (got.get("cited") or []) if c in by_id]
    return {"reply": got["answer"].strip(), "cites": cites}
