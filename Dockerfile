FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080

WORKDIR /app

COPY runner/pyproject.toml runner/uv.lock runner/README.md ./
RUN pip install --no-cache-dir uv==0.8.22 \
    && uv sync --frozen --no-dev --no-install-project

COPY runner/src ./src
RUN uv sync --frozen --no-dev \
    && chmod -R a=rX /app

USER 65532:65532
EXPOSE 8080

CMD ["sh", "-c", "uvicorn clinic_agency.main:app --host 0.0.0.0 --port ${PORT}"]
