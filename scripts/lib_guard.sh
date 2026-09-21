# 备份/恢复安全校验。被其它脚本 source。
# 禁止在未明确确认时操作开发库或生产库。

guard_db_name() {
  local name="$1"
  local kind="$2"
  if [ -z "$name" ]; then
    echo "缺少数据库名 ($kind)" >&2
    exit 2
  fi
  case "$name" in
    *_p6_db|*_itest|*_test)
      return 0
      ;;
    iam_db|audit_db|policy_db|codebook_db)
      echo "拒绝操作开发库 $name。隔离验收请使用 *_p6_db。" >&2
      exit 2
      ;;
    *prod*|*production*)
      echo "拒绝操作疑似生产库 $name" >&2
      exit 2
      ;;
    *)
      echo "数据库名 $name 不在允许的隔离名单中" >&2
      exit 2
      ;;
  esac
}
