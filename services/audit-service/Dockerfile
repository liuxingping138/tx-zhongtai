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

# 运行用户提前建好，这层永远命中缓存。/srv 保持 root 所有、appuser 只读：服务运行时不往 /srv 写文件
# （JWT 密钥写在挂载的 /secrets）。不要再 chown -R /srv，它会把整个 .venv 复制一遍，单这一步要 5 分钟。
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /srv

# 第三方依赖层只取决于 pyproject 和锁文件：先跳过公共包本身，公共包源码或本服务代码改动都不会让这层失效。
# uv 下载缓存挂在 BuildKit 缓存里，锁文件变了也只下载新增的包。
COPY packages/platform-common/pyproject.toml /srv/packages/platform-common/pyproject.toml
COPY services/audit-service/pyproject.toml services/audit-service/uv.lock services/audit-service/.python-version /srv/services/audit-service/

WORKDIR /srv/services/audit-service
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-install-package platform-common

COPY packages/platform-common /srv/packages/platform-common

COPY services/audit-service/app /srv/services/audit-service/app
COPY services/audit-service/migrations /srv/services/audit-service/migrations
COPY services/audit-service/alembic.ini /srv/services/audit-service/alembic.ini

RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project --output-file /opt/requirements.frozen.txt \
 && uv sync --frozen --no-dev

EXPOSE 8002

USER appuser

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
