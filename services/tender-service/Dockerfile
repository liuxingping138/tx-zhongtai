# syntax=docker/dockerfile:1.7
FROM python:3.12.7-slim-bookworm AS base

# uv.lock 只锁版本和哈希，不锁下载源：依赖按导出的版本清单从 PYPI_INDEX 安装（uv sync --frozen 只认锁文件里记的地址，所以不用它）。
# 换源在构建时传 --build-arg PYPI_INDEX=...，不用改锁文件。
ARG PYPI_INDEX=https://mirrors.cloud.tencent.com/pypi/simple
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    UV_DEFAULT_INDEX=$PYPI_INDEX

# uv 也从 PYPI_INDEX 装，不去 ghcr.io 拉镜像（国内很慢）。
RUN pip install --no-cache-dir --disable-pip-version-check --root-user-action=ignore --index-url "$PYPI_INDEX" uv==0.12.13

# 运行用户提前建好，这层永远命中缓存。/srv 保持 root 所有、appuser 只读：服务运行时不往 /srv 写文件
# （JWT 密钥写在挂载的 /secrets）。不要再 chown -R /srv，它会把整个 .venv 复制一遍，单这一步要 5 分钟。
RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /srv

# 第三方依赖层只取决于 pyproject 和锁文件：先跳过公共包本身，公共包源码或本服务代码改动都不会让这层失效。
# uv 下载缓存挂在 BuildKit 缓存里，锁文件变了也只下载新增的包。
COPY packages/platform-common/pyproject.toml /srv/packages/platform-common/pyproject.toml
COPY services/tender-service/pyproject.toml services/tender-service/uv.lock services/tender-service/.python-version /srv/services/tender-service/

WORKDIR /srv/services/tender-service
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project --no-emit-package platform-common --output-file /tmp/requirements.txt \
 && uv venv --quiet .venv \
 && uv pip install --python .venv/bin/python --require-hashes -r /tmp/requirements.txt

COPY packages/platform-common /srv/packages/platform-common

COPY services/tender-service/app /srv/services/tender-service/app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-project --output-file /opt/requirements.frozen.txt \
 && uv pip install --python .venv/bin/python --no-deps -e /srv/packages/platform-common -e .

EXPOSE 8006

USER appuser

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
