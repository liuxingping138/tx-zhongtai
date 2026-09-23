# syntax=docker/dockerfile:1.7
# 构建上下文必须是仓库根目录（因为需要同时拷贝 packages/platform-common）。

FROM python:3.12.7-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /srv

COPY packages/platform-common /srv/packages/platform-common
COPY services/audit-service/pyproject.toml services/audit-service/.python-version /srv/services/audit-service/

WORKDIR /srv/services/audit-service
RUN uv sync --no-dev --no-install-project

COPY services/audit-service/app /srv/services/audit-service/app
COPY services/audit-service/migrations /srv/services/audit-service/migrations
COPY services/audit-service/alembic.ini /srv/services/audit-service/alembic.ini

RUN uv sync --no-dev

EXPOSE 8002

RUN useradd --create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /srv
USER appuser

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
