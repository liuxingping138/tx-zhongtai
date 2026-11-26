#!/usr/bin/env bash
# 恢复全部服务库。目标库名必须与备份记录一致，且通过隔离名单校验。
set -euo pipefail
umask 077
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

SERVICES="iam audit policy codebook ai thinktank"

svc_upper() { echo "$1" | tr '[:lower:]' '[:upper:]'; }

for svc in $SERVICES; do
  eval "db=\${$(svc_upper "$svc")_DB_NAME:-}"
  guard_db_name "$db" "$svc"
done

# 缺任何一个服务库 dump 的备份直接拒绝，
# 避免恢复出「框架库回到备份点、业务库还是现场数据」的混合状态。
for svc in $SERVICES; do
  if [ ! -f "$BACKUP_PATH/$svc.dump" ] || [ ! -f "$BACKUP_PATH/$svc.dbname" ]; then
    echo "备份目录缺少 $svc.dump/$svc.dbname，不是全部服务库的完整备份，拒绝恢复" >&2
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

if [ -f "$BACKUP_PATH/SHA256SUMS" ]; then
  (cd "$BACKUP_PATH" && sha256sum -c SHA256SUMS)
fi

COMPOSE="${BACKUP_COMPOSE:?请设置 BACKUP_COMPOSE}"
APP_SERVICES="iam-service iam-worker audit-service audit-worker codebook-service policy-service policy-worker ai-service ai-worker thinktank-service"
echo "恢复 $BACKUP_PATH -> $IAM_DB_NAME / $AUDIT_DB_NAME / $POLICY_DB_NAME / $CODEBOOK_DB_NAME / $AI_DB_NAME / $THINKTANK_DB_NAME"

# 先停掉全部应用服务与后台 worker，保留 postgres 运行：
# 避免 pg_restore --clean 与活跃连接/锁冲突，也防止附件解包期间有写入并发。
echo "停止应用与后台 worker..."
$COMPOSE stop $APP_SERVICES

# pg_restore --no-owner 后对象属主是超级用户。GRANT 不含 ALTER/DROP，
# 随后只把当前库 public 里的表、序列、函数改回应用账号。
for svc in $SERVICES; do
  upper="$(svc_upper "$svc")"
  eval "db=\${${upper}_DB_NAME}"
  eval "app_user=\${${upper}_DB_USER}"
  if ! printf '%s' "$app_user" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]*$'; then
    echo "非法应用账号名: $app_user" >&2
    exit 2
  fi
  $COMPOSE exec -T postgres pg_restore -U "$POSTGRES_SUPERUSER" -d "$db" --clean --if-exists --no-owner --no-acl --exit-on-error --single-transaction < "$BACKUP_PATH/$svc.dump"
  $COMPOSE exec -T postgres psql -U "$POSTGRES_SUPERUSER" -d "$db" -v ON_ERROR_STOP=1 -v app_owner="$app_user" \
    < "$ROOT/scripts/assign_app_owner.sql"
  $COMPOSE exec -T postgres psql -U "$POSTGRES_SUPERUSER" -d "$db" \
    -c "GRANT ALL PRIVILEGES ON SCHEMA public TO \"${app_user}\";" \
    -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"${app_user}\";" \
    -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"${app_user}\";"
  echo "  $svc -> $db (对象属主已改为 $app_user)"
done

# 审计库不归应用账号：上面统一改成应用账号的属主再收回给超级用户，audit_events 只给应用账号查和插，删除只给清理账号。
$COMPOSE exec -T postgres sh < "$ROOT/deploy/compose/scripts/secure-audit-db.sh"

# 附件卷和库要回到同一备份点：备份目录里有附件包（backup_business.sh 产出；backup.sh 只备库，没有）就一起灌回。
# 只解包覆盖同名文件，备份之后新建的文件留着：库里已经没有引用它们，不影响页面。
# 此时应用和 worker 均已停止，用一次性容器直接挂载卷解包，确保零并发写入。
restore_files() {
  archive="$BACKUP_PATH/$1"
  service="$2"
  target="$3"
  [ -f "$archive" ] || return 0
  tar -tzf "$archive" > /dev/null
  $COMPOSE run --rm --no-deps -T "$service" tar -C "$target" -xzf - < "$archive"
  echo "  $1 -> $service:$target"
}
restore_files ai-files.tar.gz ai-service /data/ai
restore_files thinktank-files.tar.gz thinktank-service /data/thinktank

echo "重新启动应用与后台 worker..."
$COMPOSE start $APP_SERVICES
echo "恢复完成"
