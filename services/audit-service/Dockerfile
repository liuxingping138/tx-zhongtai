# syntax=docker/dockerfile:1.7
# 构建上下文必须是仓库根目录（因为需要同时拷贝 packages/platform-common）。

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
COPY services/audit-service/pyproject.toml services/audit-service/uv.lock services/audit-service/.python-version /srv/services/audit-service/

WORKDIR /srv/services/audit-service
RUN uv sync --frozen --no-dev --no-install-project

COPY services/audit-service/app /srv/services/audit-service/app
COPY services/audit-service/migrations /srv/services/audit-service/migrations
COPY services/audit-service/alembic.ini /srv/services/audit-service/alembic.ini

RUN uv export --frozen --no-dev --no-emit-project --output-file /opt/requirements.frozen.txt \
 && uv sync --frozen --no-dev

EXPOSE 8002

RUN useradd --create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /srv
USER appuser

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
