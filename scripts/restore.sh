#!/usr/bin/env bash
# 恢复 IAM 与审计库。目标库名必须与备份记录一致，且通过隔离名单校验。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib_guard.sh
source "$ROOT/scripts/lib_guard.sh"

ENV_FILE="${BACKUP_ENV_FILE:-$ROOT/deploy/compose/.p6.env}"
BACKUP_PATH="${1:-}"
if [ -z "$BACKUP_PATH" ] || [ ! -d "$BACKUP_PATH" ]; then
  echo "用法: BACKUP_COMPOSE='...' $0 deploy/backups/<stamp>" >&2
  exit 2
fi
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

dumped_iam="$(cat "$BACKUP_PATH/iam.dbname")"
dumped_audit="$(cat "$BACKUP_PATH/audit.dbname")"
if [ "$dumped_iam" != "$IAM_DB_NAME" ] || [ "$dumped_audit" != "$AUDIT_DB_NAME" ]; then
  echo "备份库名 ($dumped_iam / $dumped_audit) 与当前目标 ($IAM_DB_NAME / $AUDIT_DB_NAME) 不一致" >&2
  exit 2
fi
if [ "${RESTORE_CONFIRM:-}" != "$IAM_DB_NAME" ]; then
  echo "请设置 RESTORE_CONFIRM=$IAM_DB_NAME 以确认恢复目标" >&2
  exit 2
fi

COMPOSE="${BACKUP_COMPOSE:?请设置 BACKUP_COMPOSE}"
echo "恢复 $BACKUP_PATH -> $IAM_DB_NAME / $AUDIT_DB_NAME"
$COMPOSE exec -T postgres pg_restore -U "$POSTGRES_SUPERUSER" -d "$IAM_DB_NAME" --clean --if-exists --no-owner < "$BACKUP_PATH/iam.dump"
$COMPOSE exec -T postgres pg_restore -U "$POSTGRES_SUPERUSER" -d "$AUDIT_DB_NAME" --clean --if-exists --no-owner < "$BACKUP_PATH/audit.dump"
# pg_restore --no-owner 后表属主是超级用户，必须把应用账号权限补回去。
$COMPOSE exec -T postgres psql -U "$POSTGRES_SUPERUSER" -d "$IAM_DB_NAME" \
  -c "GRANT ALL PRIVILEGES ON SCHEMA public TO \"${IAM_DB_USER}\";" \
  -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"${IAM_DB_USER}\";" \
  -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"${IAM_DB_USER}\";"
$COMPOSE exec -T postgres psql -U "$POSTGRES_SUPERUSER" -d "$AUDIT_DB_NAME" \
  -c "GRANT ALL PRIVILEGES ON SCHEMA public TO \"${AUDIT_DB_USER}\";" \
  -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"${AUDIT_DB_USER}\";" \
  -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"${AUDIT_DB_USER}\";" \
  -c "GRANT CONNECT ON DATABASE \"${AUDIT_DB_NAME}\" TO \"${AUDIT_CLEANUP_DB_USER}\";" \
  -c "GRANT USAGE ON SCHEMA public TO \"${AUDIT_CLEANUP_DB_USER}\";"
$COMPOSE exec -T audit-service uv run python -m app.cli.grant_cleanup
echo "恢复完成"
