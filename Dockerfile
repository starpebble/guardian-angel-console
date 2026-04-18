# Guardian Angel — single image for cloud (Cloud Run, ECS, Kubernetes, etc.)
# Build: docker build -t guardian-angel .
# Run:  docker run --rm -p 8080:8080 -e PORT=8080 --env-file .env guardian-angel
#
# Uses uv + uv.lock for reproducible installs. Pass secrets at runtime only.

FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY guardian_angel ./guardian_angel/

RUN uv sync --frozen --no-dev --no-cache \
    && rm -f /usr/local/bin/uv

RUN useradd --create-home --uid 1000 --user-group --shell /usr/sbin/nologin app \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Cloud Run sets PORT; GUARDIAN_ANGEL_PORT matches local dev (developer.md / spec §8).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; p=os.environ.get('PORT') or os.environ.get('GUARDIAN_ANGEL_PORT') or '8000'; urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=3)"

CMD ["sh", "-c", "exec uvicorn guardian_angel.main:app --host 0.0.0.0 --port \"${PORT:-${GUARDIAN_ANGEL_PORT:-8000}}\""]
