"""rules/corpus.json + rules/manual.json → seed/rag_chunks.jsonl (클라우드 인계용)

한 줄 = {id, content, metadata, embedding}
임베딩은 passage 접두어를 붙여 생성한다. 조회 시에는 query 접두어를 써야 한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # ai/ 를 import 경로에

from app.tools import embed                        # noqa: E402

SOURCES = [Path("rules/corpus.json"), Path("rules/manual.json")]
OUT = Path("../seed/rag_chunks.jsonl")

HIKOREA = "https://www.hikorea.go.kr"


def source_url(d: dict) -> str:
    if d.get("doc_type") == "manual":              # 매뉴얼은 조문 링크가 없다. 쪽수는 metadata 에
        return HIKOREA
    return f"https://www.law.go.kr/법령/{quote(d['law'])}/{quote(d['article'])}"


def metadata(d: dict) -> dict:
    manual = d.get("doc_type") == "manual"
    return {
        "source_url": source_url(d),
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


def main() -> None:
    docs: list[dict] = []
    for src in SOURCES:
        if not src.exists():
            print(f"{src} 없음 — 건너뜁니다.")
            continue
        part = json.loads(src.read_text(encoding="utf-8"))
        print(f"{src}: {len(part)}조각")
        docs.extend(part)

    print(f"{len(docs)}조각 임베딩 중… (model={embed.MODEL_NAME}, dim={embed.DIM})")
    contents = [f"{d['cite']}\n{d['text']}" for d in docs]
    vecs = embed.encode(contents)          # passage 접두어는 encode 내부에서 붙는다

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for d, content, vec in zip(docs, contents, vecs):
            f.write(json.dumps({
                "id": d["id"],
                "content": content,
                "metadata": metadata(d),
                "embedding": [round(x, 6) for x in vec],
            }, ensure_ascii=False) + "\n")

    mb = OUT.stat().st_size / 1024 / 1024
    print(f"{OUT} 생성 ({mb:.1f}MB)")


if __name__ == "__main__":
    main()
