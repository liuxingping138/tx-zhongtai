#!/usr/bin/env bash
# 恢复四个服务库。目标库名必须与备份记录一致，且通过隔离名单校验。
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

SERVICES="iam audit policy codebook"

svc_upper() { echo "$1" | tr '[:lower:]' '[:upper:]'; }

for svc in $SERVICES; do
  eval "db=\${$(svc_upper "$svc")_DB_NAME:-}"
  guard_db_name "$db" "$svc"
done

# 只含 iam/audit 的旧备份缺 policy/codebook 的 dump，直接拒绝，
# 避免恢复出「框架库回到备份点、业务库还是现场数据」的混合状态。
for svc in $SERVICES; do
  if [ ! -f "$BACKUP_PATH/$svc.dump" ] || [ ! -f "$BACKUP_PATH/$svc.dbname" ]; then
    echo "备份目录缺少 $svc.dump/$svc.dbname，不是四库完整备份，拒绝恢复" >&2
    exit 2
  fi
  eval "db=\${$(svc_upper "$svc")_DB_NAME}"
  dumped="$(cat "$BACKUP_PATH/$svc.dbname")"
  if [ "$dumped" != "$db" ]; then
    echo "备份库名 $svc=$dumped 与当前目标 $db 不一致" >&2
    exit 2
  fi
done

if [ "${RESTORE_CONFIRM:-}" != "$IAM_DB_NAME" ]; then
  echo "请设置 RESTORE_CONFIRM=$IAM_DB_NAME 以确认恢复目标" >&2
  exit 2
fi

COMPOSE="${BACKUP_COMPOSE:?请设置 BACKUP_COMPOSE}"
echo "恢复 $BACKUP_PATH -> $IAM_DB_NAME / $AUDIT_DB_NAME / $POLICY_DB_NAME / $CODEBOOK_DB_NAME"

# pg_restore --no-owner 后表属主是超级用户，必须把应用账号权限补回去。
for svc in $SERVICES; do
  upper="$(svc_upper "$svc")"
  eval "db=\${${upper}_DB_NAME}"
  eval "app_user=\${${upper}_DB_USER}"
  $COMPOSE exec -T postgres pg_restore -U "$POSTGRES_SUPERUSER" -d "$db" --clean --if-exists --no-owner < "$BACKUP_PATH/$svc.dump"
  $COMPOSE exec -T postgres psql -U "$POSTGRES_SUPERUSER" -d "$db" \
    -c "GRANT ALL PRIVILEGES ON SCHEMA public TO \"${app_user}\";" \
    -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"${app_user}\";" \
    -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"${app_user}\";"
  echo "  $svc -> $db (属主权限已还给 $app_user)"
done

# 审计清理账号是只读专用账号，单独补。
$COMPOSE exec -T postgres psql -U "$POSTGRES_SUPERUSER" -d "$AUDIT_DB_NAME" \
  -c "GRANT CONNECT ON DATABASE \"${AUDIT_DB_NAME}\" TO \"${AUDIT_CLEANUP_DB_USER}\";" \
  -c "GRANT USAGE ON SCHEMA public TO \"${AUDIT_CLEANUP_DB_USER}\";"
$COMPOSE exec -T audit-service uv run python -m app.cli.grant_cleanup
echo "恢复完成"
