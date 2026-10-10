#!/usr/bin/env bash
# 把 Mac 上的源码同步到开发部署机。部署和服务器上跑 P6 共用这一份排除列表。
# 不加 --delete：否则会删掉服务器上的 .env、密钥目录和 P6 运行时文件。
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
env_value() { grep -E "^$1=" "$root/.env" | cut -d= -f2- | tr -d "\"'"; }
host="${DEPLOY_HOST:-$(env_value DEPLOY_HOST)}"
user="${DEPLOY_USER:-$(env_value DEPLOY_USER)}"
dest="${DEPLOY_DIR:-/home/$user/tx-zhongtai}"

# 后几项是本机 P6 验收和 e2e 留下的文件，含 P6 临时账号密码；服务器跑 P6 时自己生成。
rsync -az -e "ssh -i $HOME/.ssh/tx-zhongtai-deploy -o IdentitiesOnly=yes" \
  --exclude '.git/' \
  --exclude 'node_modules/' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.mypy_cache/' \
  --exclude '.coverage' \
  --exclude 'htmlcov/' \
  --exclude 'frontend/dist/' \
  --exclude '.env' \
  --exclude 'deploy/secrets/' \
  --exclude 'deploy/compose/.p6.env' \
  --exclude 'deploy/compose/.p6.runtime' \
  --exclude 'frontend/e2e/.admin-password' \
  --exclude 'frontend/test-results/' \
  --exclude 'frontend/playwright-report/' \
  "$@" "$root/" "$user@$host:$dest/"
