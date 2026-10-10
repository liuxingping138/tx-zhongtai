# syntax=docker/dockerfile:1.7
FROM python:3.12.7-slim-bookworm AS base

# 下载源在各服务 pyproject 的 [[tool.uv.index]]（阿里云）里配置并写进 uv.lock；--frozen 只认锁文件里的地址。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /usr/local/bin/

# 运行用户提前建好，这层永远命中缓存。/srv 保持 root 所有、appuser 只读：服务运行时不往 /srv 写文件
# （JWT 密钥写在挂载的 /secrets）。不要再 chown -R /srv，它会把整个 .venv 复制一遍，单这一步要 5 分钟。
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /srv

# 第三方依赖层只取决于 pyproject 和锁文件：先跳过公共包本身，公共包源码或本服务代码改动都不会让这层失效。
# uv 下载缓存挂在 BuildKit 缓存里，锁文件变了也只下载新增的包。
COPY packages/platform-common/pyproject.toml /srv/packages/platform-common/pyproject.toml
COPY services/policy-service/pyproject.toml services/policy-service/uv.lock services/policy-service/.python-version /srv/services/policy-service/

WORKDIR /srv/services/policy-service
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-install-package platform-common

COPY packages/platform-common /srv/packages/platform-common

COPY services/policy-service/app /srv/services/policy-service/app
COPY services/policy-service/migrations /srv/services/policy-service/migrations
COPY services/policy-service/alembic.ini /srv/services/policy-service/alembic.ini

RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project --output-file /opt/requirements.frozen.txt \
 && uv sync --frozen --no-dev

EXPOSE 8004

USER appuser

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
