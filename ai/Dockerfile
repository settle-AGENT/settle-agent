# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    OCR_CACHE_DIR=/tmp/ocr_cache \
    XDG_CACHE_HOME=/tmp/cache \
    HF_HOME=/app/.cache/huggingface \
    EMBED_MODEL=intfloat/multilingual-e5-small

WORKDIR /app

# WeasyPrint 는 순수 파이썬이 아니다 — Pango/cairo/GObject 를 dlopen 한다.
# 이게 없으면 PDF 생성이 런타임에 조용히 실패하고 HTML 만 남는다.
# fonts-nanum 은 서식의 한글이 두부(□)로 찍히지 않게 한다.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libglib2.0-0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libfribidi0 \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libffi8 \
        shared-mime-info \
        fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app \
    && useradd --system --gid app app \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./

RUN uv sync --frozen --no-dev --no-install-project \
    && uv cache clean

COPY app ./app
COPY rules ./rules
COPY scripts ./scripts
COPY mappings ./mappings
COPY templates ./templates

ENV PATH="/app/.venv/bin:$PATH"

# 임베딩 모델을 이미지에 굽는다 — 런타임에 HF 를 타지 않는다.
# 실패를 넘기지 않는다. 모델이 없으면 벡터 검색이 통째로 죽고, 그 사실이
# 런타임에야 드러난다. 빌드에서 잡는 편이 낫다.
RUN mkdir -p "$HF_HOME" \
    && python -c "from sentence_transformers import SentenceTransformer; import os; SentenceTransformer(os.environ['EMBED_MODEL'])"

# 코퍼스 임베딩도 미리 계산해 굽는다. 컨테이너는 이 파일을 읽어 upsert 만
# 하므로 기동이 몇 초로 끝난다 — 매번 1,600여 조각을 임베딩하지 않는다.
RUN python scripts/export_rag.py /app/rag_chunks.jsonl \
    && wc -l /app/rag_chunks.jsonl

# chown 대상을 쓰기가 필요한 곳으로 좁힌다. /app 전체를 chown 하면
# venv 가 통째로 새 레이어에 복제돼 이미지가 배로 커진다.
RUN mkdir -p "$OCR_CACHE_DIR" "$XDG_CACHE_HOME" /app/output \
    && chown -R app:app "$OCR_CACHE_DIR" "$XDG_CACHE_HOME" /app/output "$HF_HOME"

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
