"""코퍼스 → rag_chunks.jsonl (임베딩 미리 계산)

이미지 빌드 때 한 번 돌아 ai/rag_chunks.jsonl 을 굽는다. 그래야 컨테이너가
뜰 때 임베딩을 다시 계산하지 않고 upsert 만 하고 끝난다.

사용: uv run python scripts/export_rag.py [출력경로]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # ai/ 를 import 경로에

from app.tools import rag_store                    # noqa: E402


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else rag_store.BAKED
    rag_store.build(out)


if __name__ == "__main__":
    main()
