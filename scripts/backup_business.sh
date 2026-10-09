#!/usr/bin/env bash
# 四库只读备份：完整成功后原子发布；恢复仍须通过隔离库白名单。
set -euo pipefail
umask 077
if [ "${CONFIRM_BUSINESS_BACKUP:-}" != yes ]; then
  echo '请设置 CONFIRM_BUSINESS_BACKUP=yes' >&2; exit 2
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${BACKUP_ENV_FILE:-$ROOT/.env}"
set -a
source "$ENV_FILE"
set +a
: "${BACKUP_COMPOSE:?请设置 BACKUP_COMPOSE}"
BASE="${BACKUP_ROOT:-$HOME/tx-zhongtai-backups}"
STAMP="${BACKUP_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
RETENTION="${BACKUP_RETENTION_DAYS:-14}"
[[ "$STAMP" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || { echo '非法备份时间标识' >&2; exit 2; }
[[ "$RETENTION" =~ ^[0-9]+$ ]] && [ "$RETENTION" -ge 1 ] || exit 2
mkdir -p "$BASE"
chmod 700 "$BASE"
exec 9>"$BASE/.backup.lock"
flock -n 9 || { echo '已有备份执行中' >&2; exit 1; }
OUT="$BASE/$STAMP"
[ ! -e "$OUT" ] || { echo '备份目录已存在' >&2; exit 2; }
TMP="$(mktemp -d "$BASE/.incomplete.XXXXXXXX")"
trap 'rm -rf -- "$TMP"' EXIT
for pair in "iam:$IAM_DB_NAME" "audit:$AUDIT_DB_NAME" "policy:$POLICY_DB_NAME" "codebook:$CODEBOOK_DB_NAME"; do
  svc="${pair%%:*}"; db="${pair#*:}"
  [ "$db" = "${svc}_db" ] || { echo "拒绝非业务库 $db" >&2; exit 2; }
  $BACKUP_COMPOSE exec -T postgres pg_dump -U "${POSTGRES_SUPERUSER:-postgres}" -d "$db" --no-owner --format=custom > "$TMP/$svc.dump"
  $BACKUP_COMPOSE exec -T postgres pg_restore --list < "$TMP/$svc.dump" > /dev/null
  printf '%s\n' "$db" > "$TMP/$svc.dbname"
  echo "已导出 $svc"
done
(cd "$TMP" && sha256sum ./*.dump ./*.dbname > SHA256SUMS)
printf 'format=tx-zhongtai-four-db-v1\ncompleted_utc=%s\n' "$STAMP" > "$TMP/COMPLETE"
mv "$TMP" "$OUT"
# 异机目标必须由运维提供；失败退出非零并保留本地备份，不能伪报异机备份成功。
if [ -n "${BACKUP_OFFSITE:-}" ]; then
  rsync -a -- "$OUT" "$BACKUP_OFFSITE/"
  printf '%s\n' "$BACKUP_OFFSITE" > "$OUT/OFFSITE_SENT"
fi
# 只清理由本脚本生成、已完整结束且超期的目录；不清理临时文件或任意用户目录。
python3 - "$BASE" "$RETENTION" <<'PY'
import datetime, pathlib, re, shutil, sys
base=pathlib.Path(sys.argv[1]); cutoff=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=int(sys.argv[2]))
for p in base.iterdir():
    if p.is_symlink() or not p.is_dir() or not re.fullmatch(r'\d{8}T\d{6}Z',p.name): continue
    marker=p/'COMPLETE'
    if not marker.is_file() or not marker.read_text().startswith('format=tx-zhongtai-four-db-v1\n'): continue
    stamp=datetime.datetime.strptime(p.name,'%Y%m%dT%H%M%SZ').replace(tzinfo=datetime.timezone.utc)
    if stamp<cutoff: shutil.rmtree(p)
PY
echo "BACKUP_COMPLETE=$OUT"
