"""RAG 벡터 저장소 — 코퍼스를 Postgres(pgvector)에 올리고 상태를 알린다.

적재 경로가 하나뿐이어야 한다. 예전에는 셋이었고 서로 달랐다.
  load_rag.py     → rag.chunk   (입력이 gitignore 된 파일이라 배포에서 못 씀)
  index_corpus.py → law_chunk   (읽는 코드가 없는 테이블)
  export_rag.py   → jsonl 만들고 끝
qa.py 는 rag.chunk 만 읽으므로 그것만 남기고 전부 이 모듈로 모았다.

임베딩은 이미지 빌드 때 미리 계산해 BAKED 에 굽는다. 컨테이너가 뜰 때는
그 파일을 읽어 upsert 만 하므로 몇 초면 끝난다. 파일이 없으면(도커 밖 개발)
그 자리에서 임베딩한다 — 몇 분 걸린다.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from app.tools import embed

_AI_ROOT = Path(__file__).resolve().parents[2]
RULES = _AI_ROOT / "rules"
SOURCES = (RULES / "corpus.json", RULES / "manual.json")
BAKED = _AI_ROOT / "rag_chunks.jsonl"

HIKOREA = "https://www.hikorea.go.kr"

# 같은 RDS 를 여러 컨테이너가 볼 때 적재가 겹치지 않게 한다.
_LOCK_KEY = 0x5AF3_1CA7

_DDL = """
CREATE SCHEMA IF NOT EXISTS rag;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS rag.meta (
    key   text PRIMARY KEY,
    value text NOT NULL
);
"""

_CHUNK_DDL = """
CREATE TABLE IF NOT EXISTS rag.chunk (
    id        text PRIMARY KEY,
    content   text          NOT NULL,
    metadata  jsonb         NOT NULL,
    embedding vector({dim}) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunk_vec ON rag.chunk
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunk_meta ON rag.chunk USING gin (metadata);
"""


# ────────────────────────────────────────────── 코퍼스
def iter_docs() -> Iterator[dict]:
    for src in SOURCES:
        if not src.exists():
            print(f"[rag] {src} 없음 — 건너뜁니다.")
            continue
        yield from json.loads(src.read_text(encoding="utf-8"))


def _source_url(d: dict) -> str:
    if d.get("doc_type") == "manual":      # 매뉴얼은 조문 링크가 없다. 쪽수는 metadata 에
        return HIKOREA
    return f"https://www.law.go.kr/법령/{quote(d['law'])}/{quote(d['article'])}"


def metadata(d: dict) -> dict:
    manual = d.get("doc_type") == "manual"
    return {
        "source_url": _source_url(d),
        "title": d["cite"],
        "law": d["law"],
        "law_full": d["law_full"],
        "article": d["article"],
        "heading": d["heading"],
        "authority": "hikorea.go.kr" if manual else "law.go.kr",
        "doc_type": "manual" if manual else "statute",
        "visa": d.get("visa") or [],
        **({"page": d["page"], "page_end": d["page_end"]} if manual else {}),
    }


def content_of(d: dict) -> str:
    return f"{d['cite']}\n{d['text']}"


def fingerprint() -> str:
    """코퍼스 내용 + 모델 + 차원. 하나라도 바뀌면 다시 적재해야 한다."""
    h = hashlib.sha256()
    h.update(f"{embed.MODEL_NAME}:{embed.DIM}\n".encode())
    for src in SOURCES:
        h.update(src.read_bytes() if src.exists() else b"")
    return h.hexdigest()[:16]


@lru_cache(maxsize=1)
def expected_count() -> int:
    """/health 가 10초마다 불린다. 코퍼스는 안 바뀌므로 한 번만 센다."""
    return sum(1 for _ in iter_docs())


# ────────────────────────────────────────────── 굽기
def build(out: Path = BAKED) -> int:
    """코퍼스를 임베딩해 jsonl 로 쓴다. 이미지 빌드 때 한 번 돈다."""
    docs = list(iter_docs())
    if not docs:
        raise RuntimeError(f"코퍼스가 비어 있습니다: {[str(s) for s in SOURCES]}")

    print(f"[rag] {len(docs)}조각 임베딩 중… (model={embed.MODEL_NAME}, dim={embed.DIM})")
    vecs = embed.encode([content_of(d) for d in docs])   # passage 접두어는 encode 내부에서

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for d, v in zip(docs, vecs):
            f.write(json.dumps({
                "id": d["id"],
                "content": content_of(d),
                "metadata": metadata(d),
                "embedding": [round(x, 6) for x in v],
            }, ensure_ascii=False) + "\n")

    print(f"[rag] {out} — {len(docs)}행, fingerprint={fingerprint()}")
    return len(docs)


def _rows() -> list[tuple]:
    """(id, content, metadata_json, vector_literal) 목록. 구운 파일이 있으면 그걸 쓴다."""
    if BAKED.exists():
        out = []
        for line in BAKED.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            r = json.loads(line)
            out.append((r["id"], r["content"],
                        json.dumps(r["metadata"], ensure_ascii=False),
                        embed.to_pg(r["embedding"])))
        return out

    print(f"[rag] {BAKED} 없음 — 지금 임베딩합니다 (오래 걸립니다).")
    docs = list(iter_docs())
    vecs = embed.encode([content_of(d) for d in docs])
    return [(d["id"], content_of(d), json.dumps(metadata(d), ensure_ascii=False),
             embed.to_pg(v)) for d, v in zip(docs, vecs)]


# ────────────────────────────────────────────── 적재
def _get_meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM rag.meta WHERE key = %s", (key,)).fetchone()
    return row[0] if row else None


def _set_meta(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO rag.meta (key, value) VALUES (%s, %s)"
        " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))


def load(url: str | None = None, *, force: bool = False) -> dict:
    """비어 있거나 코퍼스가 바뀌었으면 적재한다. 그 외에는 아무것도 하지 않는다."""
    url = url or os.getenv("DATABASE_URL")
    if not url:
        return {"state": "off", "chunks": 0, "reason": "DATABASE_URL 없음"}

    import psycopg

    want = fingerprint()
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(_DDL)

        # 모델 차원이 바뀌면 컬럼 타입이 안 맞는다. 테이블을 새로 만든다.
        had_dim = _get_meta(conn, "dim")
        if had_dim and had_dim != str(embed.DIM):
            print(f"[rag] 차원 변경 {had_dim} → {embed.DIM}, rag.chunk 재생성")
            conn.execute("DROP TABLE IF EXISTS rag.chunk")
        conn.execute(_CHUNK_DDL.format(dim=embed.DIM))

        # 여러 컨테이너가 동시에 뜰 수 있다. 한 번에 하나만 적재한다.
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
        try:
            count = conn.execute("SELECT count(*) FROM rag.chunk").fetchone()[0]
            if not force and count > 0 and _get_meta(conn, "fingerprint") == want:
                return {"state": "ready", "chunks": count, "fingerprint": want}

            rows = _rows()
            print(f"[rag] {len(rows)}행 적재 중… (기존 {count}행, fingerprint={want})")
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO rag.chunk (id, content, metadata, embedding)
                       VALUES (%s, %s, %s::jsonb, %s::vector)
                       ON CONFLICT (id) DO UPDATE SET
                         content   = EXCLUDED.content,
                         metadata  = EXCLUDED.metadata,
                         embedding = EXCLUDED.embedding""", rows)
                # 코퍼스에서 빠진 조각은 남겨두면 검색에 계속 걸린다.
                cur.execute("DELETE FROM rag.chunk WHERE id <> ALL(%s)",
                            ([r[0] for r in rows],))

            _set_meta(conn, "fingerprint", want)
            _set_meta(conn, "dim", str(embed.DIM))
            count = conn.execute("SELECT count(*) FROM rag.chunk").fetchone()[0]
            print(f"[rag] 적재 완료 — {count}행")
            return {"state": "ready", "chunks": count, "fingerprint": want}
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))


# ────────────────────────────────────────────── 기동 시 자동 적재
_status: dict = {"state": "pending", "chunks": 0}
_lock = threading.Lock()


def status() -> dict:
    """/health 가 그대로 내보내는 값. ready 가 false 면 벡터 검색이 죽어 있다."""
    return {**_status, "expected": expected_count(),
            "ready": _status.get("state") == "ready"}


def ensure_loaded_async() -> None:
    """기동을 막지 않고 적재한다. 진행 상태는 /health 로 드러난다."""
    if not os.getenv("DATABASE_URL"):
        _status.update({"state": "off", "chunks": 0, "reason": "DATABASE_URL 없음"})
        return

    def run() -> None:
        with _lock:
            _status.update({"state": "loading"})
            try:
                _status.update(load())
            except Exception as exc:                       # noqa: BLE001
                # 여기서 죽으면 BM25 단독으로 도는데, 그 사실이 드러나야 한다.
                print(f"[rag] 적재 실패: {exc!r}")
                _status.update({"state": "error", "chunks": 0, "reason": repr(exc)})

    threading.Thread(target=run, name="rag-load", daemon=True).start()
