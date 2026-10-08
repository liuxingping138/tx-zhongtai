# syntax=docker/dockerfile:1.7
# 构建上下文必须是仓库根目录（因为需要同时拷贝 packages/platform-common）。
# 参见 deploy/compose/docker-compose.yml 中的 build.context 配置。

FROM python:3.12.7-slim-bookworm AS base

# 官方包文件从国外 CDN 下载只有几十 KB/s，大包会在 120 秒内下不完。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /srv

COPY packages/platform-common /srv/packages/platform-common
COPY services/iam-service/pyproject.toml services/iam-service/.python-version /srv/services/iam-service/

WORKDIR /srv/services/iam-service
RUN uv sync --no-dev --no-install-project

COPY services/iam-service/app /srv/services/iam-service/app
COPY services/iam-service/migrations /srv/services/iam-service/migrations
COPY services/iam-service/alembic.ini /srv/services/iam-service/alembic.ini

RUN uv sync --no-dev

EXPOSE 8001

RUN useradd --create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /srv
USER appuser

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
