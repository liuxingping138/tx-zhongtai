#!/usr/bin/env bash
# 在 P6 的 Postgres 里建专用临时库 ai_test，跑 AI提问集成测试
# （services/ai-service/tests/test_integration.py：并发认领、同模板并发发起、心跳超时、完整执行）。
# 由 make test-integration 调用，需要 P6 已经起来。测试自己会拒绝 ai_test 以外的库名。
#
# 服务器上（P6_SERVER=1）没有 uv 和 Python 3.12，pytest 借 P6 的 ai-service 镜像跑；本机直接 uv run。
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
compose="${P6_COMPOSE:?需要 P6_COMPOSE}"
docker_cmd="${DOCKER:-docker}"
# shellcheck disable=SC1091
set -a && . "$root/deploy/compose/.p6.env" && set +a

db=ai_test
# shellcheck disable=SC2086
$compose exec -T postgres sh -c "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d postgres \
  -c 'DROP DATABASE IF EXISTS $db' -c 'CREATE DATABASE $db OWNER \"$AI_DB_USER\"'" >/dev/null

# shellcheck disable=SC2086
$compose exec -T \
  -e AI_DATABASE_URL="postgresql+asyncpg://$AI_DB_USER:$AI_DB_PASSWORD@postgres:5432/$db" \
  ai-service .venv/bin/alembic upgrade head

url="postgresql+asyncpg://$AI_DB_USER:$AI_DB_PASSWORD@127.0.0.1:$POSTGRES_HOST_PORT/$db"
if [ "${P6_SERVER:-}" = "1" ]; then
  # shellcheck disable=SC2086
  $docker_cmd run --rm --network host --user 0 \
    -e PYTHONDONTWRITEBYTECODE=1 -e UV_CACHE_DIR=/uv-cache -e UV_PROJECT_ENVIRONMENT=/tmp/venv \
    -e UV_PYTHON_DOWNLOADS=never \
    -e AI_INTEGRATION=1 -e AI_DATABASE_URL="$url" -e AI_DATA_DIR=/tmp/ai-data \
    -v tx-zhongtai-p6-uv-cache:/uv-cache \
    -v "$root/packages:/work/packages:ro" -v "$root/services/ai-service:/work/services/ai-service:ro" \
    -w /work/services/ai-service \
    tx-zhongtai-p6-ai-service:latest \
    sh -c "uv sync --frozen --extra dev --quiet && uv run --no-sync pytest -q -p no:cacheprovider tests/test_integration.py"
else
  (cd "$root/services/ai-service" && AI_INTEGRATION=1 AI_DATABASE_URL="$url" \
    uv run pytest -q -p no:cacheprovider tests/test_integration.py)
fi
