# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    OCR_CACHE_DIR=/tmp/ocr_cache \
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

RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY rules ./rules
COPY mappings ./mappings
COPY templates ./templates

ENV PATH="/app/.venv/bin:$PATH"

# 임베딩 모델을 이미지에 굽는다 — 런타임에 HF 를 타지 않는다.
RUN mkdir -p "$HF_HOME" \
    && python -c "from sentence_transformers import SentenceTransformer; import os; SentenceTransformer(os.environ['EMBED_MODEL'])" \
    || echo "WARN: 임베딩 모델 사전 다운로드 실패 — 런타임에 재시도한다."

RUN mkdir -p "$OCR_CACHE_DIR" /app/output \
    && chown -R app:app /app "$OCR_CACHE_DIR"

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
