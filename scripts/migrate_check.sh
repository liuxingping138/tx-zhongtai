#!/usr/bin/env bash
# 模型与数据库漂移检查。任一服务失败都必须让调用方看到非零退出码。
set -euo pipefail

if [ -n "${COMPOSE_CMD:-}" ]; then
  # shellcheck disable=SC2206
  compose=( $COMPOSE_CMD )
else
  root="$(cd "$(dirname "$0")/.." && pwd)"
  compose=(docker compose -f "$root/deploy/compose/docker-compose.yml" --env-file "$root/.env")
fi

services=(iam-service audit-service codebook-service policy-service ai-service)
for name in "${services[@]}"; do
  printf '%-20s ' "$name"
  "${compose[@]}" exec -T "$name" .venv/bin/alembic check
  printf '\n'
done
