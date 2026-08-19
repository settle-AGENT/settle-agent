"""rules/corpus.json → Postgres(pgvector) 색인

사용: uv run python scripts/index_corpus.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(".env")

from app.tools import embed                        # noqa: E402

CORPUS = Path("rules/corpus.json")

DDL = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS law_chunk (
    id        text PRIMARY KEY,
    law       text NOT NULL,
    article   text NOT NULL,
    heading   text NOT NULL,
    cite      text NOT NULL,
    body      text NOT NULL,
    embedding vector({embed.DIM})
);
CREATE INDEX IF NOT EXISTS law_chunk_vec
    ON law_chunk USING hnsw (embedding vector_cosine_ops);
"""


def main() -> None:
    docs = json.loads(CORPUS.read_text(encoding="utf-8"))
    print(f"{len(docs)}개 조문 임베딩 중…")

    # 제목을 붙여서 임베딩하면 조문 주제가 벡터에 더 잘 실린다
    vecs = embed.encode([f"{d['cite']}\n{d['text']}" for d in docs])

    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(DDL)
        conn.execute("TRUNCATE law_chunk;")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO law_chunk (id, law, article, heading, cite, body, embedding)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s::vector)",
                [(d["id"], d["law"], d["article"], d["heading"], d["cite"],
                  d["text"], embed.to_pg(v)) for d, v in zip(docs, vecs)])
    print("색인 완료")


if __name__ == "__main__":
    main()