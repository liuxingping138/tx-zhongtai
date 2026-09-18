# syntax=docker/dockerfile:1.7
FROM python:3.12.7-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /srv

COPY packages/platform-common /srv/packages/platform-common
COPY services/policy-service/pyproject.toml services/policy-service/.python-version /srv/services/policy-service/

WORKDIR /srv/services/policy-service
RUN uv sync --no-dev --no-install-project

COPY services/policy-service/app /srv/services/policy-service/app
COPY services/policy-service/migrations /srv/services/policy-service/migrations
COPY services/policy-service/alembic.ini /srv/services/policy-service/alembic.ini

RUN uv sync --no-dev

EXPOSE 8004

RUN useradd --create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /srv
USER appuser

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
