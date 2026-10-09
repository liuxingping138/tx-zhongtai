# syntax=docker/dockerfile:1.7
FROM python:3.12.7-slim-bookworm AS base

# 官方包文件从国外 CDN 下载只有几十 KB/s，大包会在 120 秒内下不完。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /usr/local/bin/

WORKDIR /srv

COPY packages/platform-common /srv/packages/platform-common
COPY services/codebook-service/pyproject.toml services/codebook-service/uv.lock services/codebook-service/.python-version /srv/services/codebook-service/

WORKDIR /srv/services/codebook-service
RUN uv sync --frozen --no-dev --no-install-project

COPY services/codebook-service/app /srv/services/codebook-service/app
COPY services/codebook-service/migrations /srv/services/codebook-service/migrations
COPY services/codebook-service/alembic.ini /srv/services/codebook-service/alembic.ini
COPY services/codebook-service/data /srv/services/codebook-service/data

RUN uv export --frozen --no-dev --no-emit-project --output-file /opt/requirements.frozen.txt \
 && uv sync --frozen --no-dev

EXPOSE 8003

RUN useradd --create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /srv
USER appuser

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
