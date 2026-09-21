# syntax=docker/dockerfile:1.7
FROM python:3.12.7-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /srv

COPY packages/platform-common /srv/packages/platform-common
COPY services/codebook-service/pyproject.toml services/codebook-service/.python-version /srv/services/codebook-service/

WORKDIR /srv/services/codebook-service
RUN uv sync --no-dev --no-install-project

COPY services/codebook-service/app /srv/services/codebook-service/app
COPY services/codebook-service/migrations /srv/services/codebook-service/migrations
COPY services/codebook-service/alembic.ini /srv/services/codebook-service/alembic.ini
COPY services/codebook-service/data /srv/services/codebook-service/data

RUN uv sync --no-dev

EXPOSE 8003

RUN useradd --create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /srv
USER appuser

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
