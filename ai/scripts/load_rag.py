"""seed/rag_chunks.jsonl → Postgres(pgvector). 로컬·RDS 동일하게 반복 적재.

사용: DATABASE_URL=... uv run python scripts/load_rag.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(".env")

SRC = Path("../seed/rag_chunks.jsonl")
DIM = 384

DDL = f"""
CREATE SCHEMA IF NOT EXISTS rag;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS rag.chunk (
    id        text PRIMARY KEY,
    content   text        NOT NULL,
    metadata  jsonb       NOT NULL,
    embedding vector({DIM}) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunk_vec ON rag.chunk
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunk_meta ON rag.chunk USING gin (metadata);
"""


def main() -> None:
    rows = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines() if l]
    print(f"{len(rows)}행 적재 중…")

    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        conn.execute(DDL)
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO rag.chunk (id, content, metadata, embedding)
                   VALUES (%s, %s, %s::jsonb, %s::vector)
                   ON CONFLICT (id) DO UPDATE SET
                     content = EXCLUDED.content,
                     metadata = EXCLUDED.metadata,
                     embedding = EXCLUDED.embedding""",
                [(r["id"], r["content"], json.dumps(r["metadata"], ensure_ascii=False),
                  "[" + ",".join(map(str, r["embedding"])) + "]") for r in rows])
    print("완료")


if __name__ == "__main__":
    main()