# syntax=docker/dockerfile:1.7
FROM python:3.12.7-slim-bookworm AS base

ARG PYPI_INDEX=https://mirrors.cloud.tencent.com/pypi/simple
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    UV_DEFAULT_INDEX=$PYPI_INDEX

RUN pip install --no-cache-dir --disable-pip-version-check --root-user-action=ignore --index-url "$PYPI_INDEX" uv==0.12.13

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /srv

COPY packages/platform-common/pyproject.toml /srv/packages/platform-common/pyproject.toml
COPY services/thinktank-service/pyproject.toml services/thinktank-service/uv.lock services/thinktank-service/.python-version /srv/services/thinktank-service/

WORKDIR /srv/services/thinktank-service
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project --no-emit-package platform-common --output-file /tmp/requirements.txt \
 && uv venv --quiet .venv \
 && uv pip install --python .venv/bin/python --require-hashes -r /tmp/requirements.txt

COPY packages/platform-common /srv/packages/platform-common

COPY services/thinktank-service/app /srv/services/thinktank-service/app
COPY services/thinktank-service/data /srv/services/thinktank-service/data
COPY services/thinktank-service/migrations /srv/services/thinktank-service/migrations
COPY services/thinktank-service/alembic.ini /srv/services/thinktank-service/alembic.ini

RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project --output-file /opt/requirements.frozen.txt \
 && uv pip install --python .venv/bin/python --no-deps -e /srv/packages/platform-common -e . \
 && mkdir -p /data/thinktank \
 && chown appuser:appuser /data/thinktank

EXPOSE 8007

USER appuser

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--timeout-keep-alive", "75", "--port", "8007"]
