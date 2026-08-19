# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    OCR_CACHE_DIR=/tmp/ocr_cache

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app app \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./

RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY rules ./rules
COPY mappings ./mappings
COPY templates ./templates

RUN mkdir -p "$OCR_CACHE_DIR" \
    && chown -R app:app /app "$OCR_CACHE_DIR"

ENV PATH="/app/.venv/bin:$PATH"

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
