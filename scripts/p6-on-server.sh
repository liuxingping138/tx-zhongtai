#!/usr/bin/env bash
# 在 Mac 上执行：同步源码后，在开发部署机上跑 P6 隔离验收（集成 + e2e），结束一定 p6-down。
#   bash scripts/p6-on-server.sh                # 集成 + e2e
#   bash scripts/p6-on-server.sh integration    # 只跑集成
# P6 与业务栈同机但互不相干：项目名 tx-zhongtai-p6、独立卷/网络/库，网关只绑 127.0.0.1:8090。
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
env_value() { grep -E "^$1=" "$root/.env" | cut -d= -f2- | tr -d "\"'"; }
host="${DEPLOY_HOST:-$(env_value DEPLOY_HOST)}"
user="${DEPLOY_USER:-$(env_value DEPLOY_USER)}"
sudo_pass="${DEPLOY_SUDO_PASSWORD:-$(env_value DEPLOY_SUDO_PASSWORD)}"
dest="${DEPLOY_DIR:-$(env_value DEPLOY_DIR)}"
dest="${dest:-/home/$user/tx-zhongtai}"
targets="test-integration test-e2e"
[ "${1:-}" = "integration" ] && targets="test-integration"

bash "$root/scripts/sync-to-server.sh"

# 密码经 stdin 交给远端，再由 askpass 脚本交给 sudo；不出现在命令行参数和磁盘上。
printf '%s\n' "$sudo_pass" | ssh -i "$HOME/.ssh/tx-zhongtai-deploy" -o IdentitiesOnly=yes "$user@$host" \
  "cd $dest && IFS= read -r P6_SUDO_PASSWORD && export P6_SUDO_PASSWORD \
   SUDO_ASKPASS=\$PWD/scripts/sudo-askpass-env.sh && \
   chmod +x scripts/sudo-askpass-env.sh && \
   sudo -A install -d -o \$(id -u) -g \$(id -g) deploy/secrets/jwt-p6 && \
   opts='P6_SERVER=1' && \
   rc=0; make \$opts $targets || rc=\$?; \
   [ \$rc -eq 0 ] || make --no-print-directory \$opts p6-logs 2>&1 | tail -120; \
   make \$opts p6-down >/dev/null 2>&1 || echo 'p6-down 失败，请手动清理 tx-zhongtai-p6'; \
   rm -rf deploy/compose/.p6.runtime frontend/e2e/.admin-password; \
   exit \$rc"
