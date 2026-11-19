#!/usr/bin/env bash
# 业务库只读备份：五个服务库 + AI提问的附件卷，完整成功后原子发布；恢复仍须通过隔离库白名单。
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
# 默认写在 /data：服务器根分区只有 20G、同机还有别的业务，AI 附件卷动辄几十 G，写在 $HOME（/root）会把根分区写满。
if [ -z "${BACKUP_ROOT:-}" ] && [ -d /data ]; then BACKUP_ROOT=/data/tx-zhongtai-backups; fi
BASE="${BACKUP_ROOT:-$HOME/tx-zhongtai-backups}"
MIN_FREE_GB="${BACKUP_MIN_FREE_GB:-10}"
STAMP="${BACKUP_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
RETENTION="${BACKUP_RETENTION_DAYS:-14}"
[[ "$STAMP" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || { echo '非法备份时间标识' >&2; exit 2; }
[[ "$RETENTION" =~ ^[0-9]+$ ]] && [ "$RETENTION" -ge 1 ] || exit 2
mkdir -p "$BASE"
chmod 700 "$BASE"
FREE_GB=$(( $(df -Pk "$BASE" | awk 'NR==2 {print $4}') / 1024 / 1024 ))
[ "$FREE_GB" -ge "$MIN_FREE_GB" ] || { echo "备份目录所在分区只剩 ${FREE_GB}G，少于 ${MIN_FREE_GB}G，不备份" >&2; exit 1; }
exec 9>"$BASE/.backup.lock"
flock -n 9 || { echo '已有备份执行中' >&2; exit 1; }
OUT="$BASE/$STAMP"
[ ! -e "$OUT" ] || { echo '备份目录已存在' >&2; exit 2; }
TMP="$(mktemp -d "$BASE/.incomplete.XXXXXXXX")"
trap 'rm -rf -- "$TMP"' EXIT
for pair in "iam:$IAM_DB_NAME" "audit:$AUDIT_DB_NAME" "policy:$POLICY_DB_NAME" "codebook:$CODEBOOK_DB_NAME" "ai:$AI_DB_NAME" "thinktank:${THINKTANK_DB_NAME:-thinktank_db}"; do
  svc="${pair%%:*}"; db="${pair#*:}"
  [ "$db" = "${svc}_db" ] || { echo "拒绝非业务库 $db" >&2; exit 2; }
  $BACKUP_COMPOSE exec -T postgres pg_dump -U "${POSTGRES_SUPERUSER:-postgres}" -d "$db" --no-owner --format=custom > "$TMP/$svc.dump"
  $BACKUP_COMPOSE exec -T postgres pg_restore --list < "$TMP/$svc.dump" > /dev/null
  printf '%s\n' "$db" > "$TMP/$svc.dbname"
  echo "已导出 $svc"
done
# 模板 Excel、码表和批量结果不在库里，在 ai-service 的持久卷上，一起打包并压缩（原始返回 CSV 压缩比很高）。
# 批量任务常跑几个小时：备份时正在追加的 temp.csv、刚换掉的结果文件会让 GNU tar 报「file changed」退出 1，
# 这类只是警告，拿到的是那一刻的内容；退出码 2 以上才是真出错。
set +e
$BACKUP_COMPOSE exec -T ai-service tar --warning=no-file-changed --ignore-failed-read -C /data/ai -czf - . > "$TMP/ai-files.tar.gz"
TAR_STATUS=$?
set -e
[ "$TAR_STATUS" -le 1 ] || { echo "打包 AI提问附件失败（tar 退出码 $TAR_STATUS）" >&2; exit 1; }
tar -tzf "$TMP/ai-files.tar.gz" > /dev/null
echo "已打包 AI提问附件"
set +e
$BACKUP_COMPOSE exec -T thinktank-service tar --warning=no-file-changed --ignore-failed-read -C /data/thinktank -czf - . > "$TMP/thinktank-files.tar.gz"
TT_TAR_STATUS=$?
set -e
[ "$TT_TAR_STATUS" -le 1 ] || { echo "打包智库附件失败（tar 退出码 $TT_TAR_STATUS）" >&2; exit 1; }
tar -tzf "$TMP/thinktank-files.tar.gz" > /dev/null
echo "已打包智库附件"
(cd "$TMP" && sha256sum ./*.dump ./*.dbname ./ai-files.tar.gz ./thinktank-files.tar.gz > SHA256SUMS)
printf 'format=tx-zhongtai-business-v3\ncompleted_utc=%s\n' "$STAMP" > "$TMP/COMPLETE"
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
    if not marker.is_file() or not marker.read_text().startswith(('format=tx-zhongtai-four-db-v1\n','format=tx-zhongtai-business-v2\n','format=tx-zhongtai-business-v3\n')): continue
    stamp=datetime.datetime.strptime(p.name,'%Y%m%dT%H%M%SZ').replace(tzinfo=datetime.timezone.utc)
    if stamp<cutoff: shutil.rmtree(p)
PY
echo "BACKUP_COMPLETE=$OUT"
