#!/usr/bin/env bash
# 备份 IAM 与审计库。默认只允许隔离库名（*_p6_db / *_itest / *_test）。
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

guard_db_name "$IAM_DB_NAME" iam
guard_db_name "$AUDIT_DB_NAME" audit

COMPOSE="${BACKUP_COMPOSE:?请设置 BACKUP_COMPOSE，例如 docker compose -p tx-zhongtai-p6 ...}"
STAMP="${BACKUP_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT_DIR="${BACKUP_DIR:-$ROOT/deploy/backups/$STAMP}"
mkdir -p "$OUT_DIR"

echo "备份到 $OUT_DIR"
$COMPOSE exec -T postgres pg_dump -U "$POSTGRES_SUPERUSER" -d "$IAM_DB_NAME" --no-owner --format=custom > "$OUT_DIR/iam.dump"
$COMPOSE exec -T postgres pg_dump -U "$POSTGRES_SUPERUSER" -d "$AUDIT_DB_NAME" --no-owner --format=custom > "$OUT_DIR/audit.dump"
printf '%s\n' "$IAM_DB_NAME" > "$OUT_DIR/iam.dbname"
printf '%s\n' "$AUDIT_DB_NAME" > "$OUT_DIR/audit.dbname"
echo "备份完成 $STAMP"
echo "$OUT_DIR"
