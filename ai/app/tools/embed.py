"""로컬 다국어 임베딩.

외부 API를 쓰지 않는다 — 질문 원문이 서버 밖으로 나가지 않는다.
multilingual-e5-small: 384차원, CPU에서 충분히 빠르다.
"""
from __future__ import annotations

import os
from functools import lru_cache

MODEL_NAME = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
DIM = 384


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def available() -> bool:
    try:
        _model()
        return True
    except Exception as exc:                       # noqa: BLE001
        print(f"[embed] 모델 로드 실패: {exc!r}")
        return False


def encode(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
    """e5 계열은 query/passage 접두어를 요구한다."""
    prefix = "query: " if is_query else "passage: "
    vecs = _model().encode([prefix + t for t in texts],
                           normalize_embeddings=True,
                           batch_size=32, show_progress_bar=False)
    return [v.tolist() for v in vecs]


def to_pg(vec: list[float]) -> str:
    """pgvector 리터럴. 별도 어댑터 없이 ::vector 로 캐스팅한다."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def warm() -> None:
    """첫 질문이 느리지 않게 서버 기동 시 미리 올린다."""
    try:
        encode(["warmup"], is_query=True)
        print(f"[embed] {MODEL_NAME} 준비됨")
    except Exception as exc:                       # noqa: BLE001
        print(f"[embed] 워밍업 실패, BM25로만 동작: {exc!r}")