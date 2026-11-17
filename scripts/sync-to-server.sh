#!/usr/bin/env bash
# 把 Mac 上的源码同步到开发部署机。部署和服务器上跑 P6 共用这一份排除列表。
# 带 --delete：本地删掉的文件在服务器上也删掉，否则会残留并被打进镜像、让 e2e 找到已删除的用例。
# 被 --exclude 的路径在服务器上不会被删除，服务器独有的 .env、密钥目录、P6 运行时文件都靠这份清单保护；
# 往服务器上新增本地没有的文件或目录时，必须先加进下面的排除列表。
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
env_value() { grep -E "^$1=" "$root/.env" | cut -d= -f2- | tr -d "\"'"; }
host="${DEPLOY_HOST:-$(env_value DEPLOY_HOST)}"
user="${DEPLOY_USER:-$(env_value DEPLOY_USER)}"
dest="${DEPLOY_DIR:-$(env_value DEPLOY_DIR)}"
dest="${dest:-/data/tx-zhongtai}"

# 同步到生产目录的必须是提交过的代码：带着没提交、没测过的改动推过去，下一次 up --build 就进了生产，
# 网关的动态配置（watch: true）更是立刻生效。P6 走 scripts/p6-on-server.sh，同步到单独的目录，允许没提交。
if [ -z "${ALLOW_DIRTY:-}" ] && [ -n "$(git -C "$root" status --porcelain)" ]; then
  echo "工作区有没提交的改动，不同步到 $dest。先提交；只想跑 P6 用 scripts/p6-on-server.sh。" >&2
  exit 1
fi

# 依赖与缓存在服务器上各自生成；后半段是服务器独有或含密码的文件。
rsync -az --delete -e "ssh -i $HOME/.ssh/tx-zhongtai-deploy -o IdentitiesOnly=yes" \
  --exclude '.git/' \
  --exclude 'node_modules/' \
  --exclude '.pnpm-store/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.mypy_cache/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '.import_linter_cache/' \
  --exclude '.coverage' \
  --exclude 'htmlcov/' \
  --exclude 'frontend/dist/' \
  --exclude 'frontend/.vite/' \
  --exclude '.DS_Store' \
  --exclude '.claude/' \
  --exclude '.cursor/' \
  --exclude '.env' \
  --exclude '/.env.*' \
  --exclude '*.bak' \
  --exclude 'deploy/secrets/' \
  --exclude 'deploy/backups/' \
  --exclude 'deploy/compose/.p6.*' \
  --exclude 'frontend/e2e/.admin-password' \
  --exclude 'frontend/test-results/' \
  --exclude 'frontend/playwright-report/' \
  --exclude '.playwright-mcp/' \
  --exclude '内部平台角色权限表.xlsx' \
  "$@" "$root/" "$user@$host:$dest/"
