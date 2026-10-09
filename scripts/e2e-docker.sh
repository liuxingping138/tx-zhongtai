#!/usr/bin/env bash
# 在 Playwright 官方镜像里跑 e2e，宿主机不用装 Node、pnpm 和浏览器（服务器上用）。
# 镜像版本必须与 frontend/package.json 的 @playwright/test 一致，否则浏览器版本对不上。
# 用 --network host 访问只绑在 127.0.0.1 的 P6 网关；--user 保证生成的 node_modules、
# test-results 属于部署用户，后续 rsync 和清理不会撞上 root 文件。
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
docker_cmd="${DOCKER:-docker}"
version="$(sed -nE 's/.*"@playwright\/test": "([0-9.]+)".*/\1/p' "$root/frontend/package.json")"
pnpm_version="12.4.1" # 与 frontend/Dockerfile 一致
runtime_file="$root/deploy/compose/.p6.runtime"
test -f "$runtime_file" || { echo "缺少 $runtime_file，请先运行 make test-integration"; exit 2; }

# shellcheck disable=SC2086
$docker_cmd run --rm --network host --ipc=host \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp/home -e npm_config_cache=/tmp/npm-cache \
  -e P6_GATEWAY="${P6_GATEWAY:?}" \
  --env-file "$runtime_file" \
  -v "$root/frontend:/work" -w /work \
  "mcr.microsoft.com/playwright:v${version}-noble" \
  sh -c "npx -y pnpm@${pnpm_version} install --frozen-lockfile --reporter=silent && npx -y pnpm@${pnpm_version} exec playwright test $*"
