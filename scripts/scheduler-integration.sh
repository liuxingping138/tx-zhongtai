#!/usr/bin/env bash
# 在 P6 的 Postgres 里建专用临时库 scheduler_test，跑任务调度集成测试
# （services/policy-service/tests/test_scheduler_integration.py：并发领取、停机合并、重试、重启恢复等）。
# 由 make test-integration 调用，需要 P6 已经起来。测试自己会拒绝 scheduler_test 以外的库名。
#
# 服务器上（P6_SERVER=1）没有 uv 和 Python 3.12，pytest 借 P6 的政策服务镜像跑（自带 Python 3.12 和 uv）；本机直接 uv run。
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
compose="${P6_COMPOSE:?需要 P6_COMPOSE}"
docker_cmd="${DOCKER:-docker}"
# shellcheck disable=SC1091
set -a && . "$root/deploy/compose/.p6.env" && set +a

db=scheduler_test
# shellcheck disable=SC2086
$compose exec -T postgres sh -c "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d postgres \
  -c 'DROP DATABASE IF EXISTS $db' -c 'CREATE DATABASE $db OWNER \"$POLICY_DB_USER\"'" >/dev/null

# 迁移用 P6 的政策服务镜像跑，和线上同一份迁移脚本。
# shellcheck disable=SC2086
$compose exec -T \
  -e POLICY_DATABASE_URL="postgresql+asyncpg://$POLICY_DB_USER:$POLICY_DB_PASSWORD@postgres:5432/$db" \
  policy-service .venv/bin/alembic upgrade head

url="postgresql+asyncpg://$POLICY_DB_USER:$POLICY_DB_PASSWORD@127.0.0.1:$POSTGRES_HOST_PORT/$db"
if [ "${P6_SERVER:-}" = "1" ]; then
  # 源码只读挂载、依赖装在容器内临时目录，不往宿主机写任何文件；下载缓存放命名卷，下次只下载新增的包。
  # shellcheck disable=SC2086
  $docker_cmd run --rm --network host --user 0 \
    -e PYTHONDONTWRITEBYTECODE=1 -e UV_CACHE_DIR=/uv-cache -e UV_PROJECT_ENVIRONMENT=/tmp/venv \
    -e UV_PYTHON_DOWNLOADS=never \
    -e SCHEDULER_INTEGRATION=1 -e POLICY_DATABASE_URL="$url" \
    -v tx-zhongtai-p6-uv-cache:/uv-cache \
    -v "$root/packages:/work/packages:ro" -v "$root/services/policy-service:/work/services/policy-service:ro" \
    -w /work/services/policy-service \
    tx-zhongtai-p6-policy-service:latest \
    sh -c "uv sync --frozen --extra dev --quiet && uv run --no-sync pytest -q -p no:cacheprovider tests/test_scheduler_integration.py tests/test_aitag_integration.py"
else
  (cd "$root/services/policy-service" && SCHEDULER_INTEGRATION=1 POLICY_DATABASE_URL="$url" \
    uv run pytest -q -p no:cacheprovider tests/test_scheduler_integration.py tests/test_aitag_integration.py)
fi
