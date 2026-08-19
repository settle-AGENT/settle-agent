"""법령 질의응답 — 하이브리드 검색 후 LLM이 검색된 조문 안에서만 답한다.

벡터(pgvector)가 의미를, BM25가 조문 번호·고유 표현을 잡는다.
두 순위를 RRF로 합친다. DB나 모델이 없으면 BM25 단독으로 동작한다.
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

CORPUS = Path(__file__).resolve().parents[2] / "rules" / "corpus.json"

ALIAS = {
    "이사": "체류지 변경신고", "전입": "체류지 변경신고",
    "알바": "시간제취업 체류자격 외 활동", "아르바이트": "시간제취업 체류자격 외 활동",
    "취업": "체류자격 외 활동 근무처", "계좌": "금융거래 실명 예금",
    "통장": "금융거래 실명 예금", "등록증": "외국인등록증", "비자": "체류자격",
    "연장": "체류기간 연장허가", "송금": "외국환 지급", "과태료": "과태료 벌칙",
    "신분증": "실지명의 실명확인", "유학생": "외국인유학생",
}

_STRIP = re.compile(r"[^가-힣A-Za-z0-9]")
_RRF_K = 60          # Reciprocal Rank Fusion 상수
_POOL = 8            # 각 검색기가 내놓는 후보 수
_TOP = 4             # LLM에 넘길 조문 수


# ────────────────────────────────────────────── 코퍼스 · BM25
def _grams(s: str) -> list[str]:
    s = _STRIP.sub("", s)
    return [s[i:i + 2] for i in range(len(s) - 1)] or ([s] if s else [])


@lru_cache(maxsize=1)
def _index():
    if not CORPUS.exists():
        return [], [], [], 1.0, Counter(), 0
    docs = json.loads(CORPUS.read_text(encoding="utf-8"))
    toks = [Counter(_grams(d["heading"] * 3 + d["text"])) for d in docs]
    lens = [sum(c.values()) for c in toks]
    avg = (sum(lens) / len(lens)) if lens else 1.0
    df = Counter()
    for c in toks:
        df.update(c.keys())
    return docs, toks, lens, avg, df, len(docs)


def available() -> bool:
    return _index()[5] > 0


def _expand(q: str) -> str:
    return q + " " + " ".join(v for k, v in ALIAS.items() if k in q)


def _bm25(query: str, k: int, k1: float = 1.4, b: float = 0.75) -> list[str]:
    docs, toks, lens, avg, df, n = _index()
    if not n:
        return []
    qg = Counter(_grams(_expand(query)))
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
def search(query: str, k: int = _TOP) -> list[dict]:
    docs = _index()[0]
    if not docs:
        return []
    by_id = {d["id"]: d for d in docs}

    ranks = defaultdict(float)
    used = {"vector": _vector(query, _POOL), "bm25": _bm25(query, _POOL)}
    for names in used.values():
        for pos, doc_id in enumerate(names):
            ranks[doc_id] += 1.0 / (_RRF_K + pos + 1)

    if not ranks:
        return []

    top = sorted(ranks.items(), key=lambda kv: kv[1], reverse=True)[:k]
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

    hits = search(_retrieval_query(question, history))

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
