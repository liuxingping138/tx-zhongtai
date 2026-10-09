#!/usr/bin/env bash
# alembic check 失败时，门禁脚本必须返回同一个非零退出码。
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/fake-compose" << 'EOF'
#!/usr/bin/env bash
echo "ERROR alembic check failed" >&2
exit 42
EOF
chmod +x "$tmp/fake-compose"
set +e
COMPOSE_CMD="$tmp/fake-compose" bash "$root/scripts/migrate_check.sh" >"$tmp/out" 2>"$tmp/err"
code=$?
set -e
if [ "$code" -ne 42 ]; then
  echo "migrate-check 退出码是 $code，应当是 42" >&2
  cat "$tmp/err" >&2
  exit 1
fi
if ! grep -q "ERROR alembic check failed" "$tmp/err"; then
  echo "没有保留 alembic 的错误输出" >&2
  exit 1
fi
echo "migrate_check_failure_propagates"
