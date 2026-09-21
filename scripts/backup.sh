#!/usr/bin/env bash
# 备份四个服务库。默认只允许隔离库名（*_p6_db / *_itest / *_test）。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib_guard.sh
source "$ROOT/scripts/lib_guard.sh"

ENV_FILE="${BACKUP_ENV_FILE:-$ROOT/deploy/compose/.p6.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "缺少 $ENV_FILE" >&2
  exit 2
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# 每个服务一套独立库，四个都要备。只备 iam+audit 会丢掉全部业务数据。
SERVICES="iam audit policy codebook"
for svc in $SERVICES; do
  eval "db=\${$(echo "$svc" | tr '[:lower:]' '[:upper:]')_DB_NAME:-}"
  guard_db_name "$db" "$svc"
done

COMPOSE="${BACKUP_COMPOSE:?请设置 BACKUP_COMPOSE，例如 docker compose -p tx-zhongtai-p6 ...}"
STAMP="${BACKUP_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT_DIR="${BACKUP_DIR:-$ROOT/deploy/backups/$STAMP}"
mkdir -p "$OUT_DIR"

echo "备份到 $OUT_DIR"
for svc in $SERVICES; do
  eval "db=\${$(echo "$svc" | tr '[:lower:]' '[:upper:]')_DB_NAME}"
  $COMPOSE exec -T postgres pg_dump -U "$POSTGRES_SUPERUSER" -d "$db" --no-owner --format=custom > "$OUT_DIR/$svc.dump"
  printf '%s\n' "$db" > "$OUT_DIR/$svc.dbname"
  echo "  $svc <- $db"
done
echo "备份完成 $STAMP"
echo "$OUT_DIR"
