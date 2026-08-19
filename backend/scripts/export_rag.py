"""rules/corpus.json → seed/rag_chunks.jsonl (클라우드 인계용)

한 줄 = {id, content, metadata, embedding}
임베딩은 passage 접두어를 붙여 생성한다. 조회 시에는 query 접두어를 써야 한다.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from app.tools import embed

CORPUS = Path("rules/corpus.json")
OUT = Path("../seed/rag_chunks.jsonl")


def source_url(law: str, article: str) -> str:
    return f"https://www.law.go.kr/법령/{quote(law)}/{quote(article)}"


def main() -> None:
    docs = json.loads(CORPUS.read_text(encoding="utf-8"))
    print(f"{len(docs)}개 조문 임베딩 중… (model={embed.MODEL_NAME}, dim={embed.DIM})")

    contents = [f"{d['cite']}\n{d['text']}" for d in docs]
    vecs = embed.encode(contents)          # passage 접두어는 encode 내부에서 붙는다

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for d, content, vec in zip(docs, contents, vecs):
            f.write(json.dumps({
                "id": d["id"],
                "content": content,
                "metadata": {
                    "source_url": source_url(d["law"], d["article"]),
                    "title": d["cite"],
                    "law": d["law"],
                    "law_full": d["law_full"],
                    "article": d["article"],
                    "heading": d["heading"],
                    "authority": "law.go.kr",
                    "doc_type": "statute",
                    "visa": [],
                },
                "embedding": [round(x, 6) for x in vec],
            }, ensure_ascii=False) + "\n")

    mb = OUT.stat().st_size / 1024 / 1024
    print(f"{OUT} 생성 ({mb:.1f}MB)")


if __name__ == "__main__":
    main()