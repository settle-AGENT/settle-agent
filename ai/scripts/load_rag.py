"""코퍼스 → Postgres(pgvector). 로컬·RDS 동일하게 반복 적재.

평소에는 AI 서버가 기동할 때 알아서 한다(app/tools/rag_store.py).
이 스크립트는 서버를 띄우지 않고 손으로 채우거나 강제로 다시 넣을 때 쓴다.

사용: DATABASE_URL=... uv run python scripts/load_rag.py [--force]
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # ai/ 를 import 경로에
load_dotenv(".env")

from app.tools import rag_store                    # noqa: E402


def main() -> None:
    result = rag_store.load(force="--force" in sys.argv)
    print(result)
    if result.get("state") != "ready":
        sys.exit(1)


if __name__ == "__main__":
    main()
