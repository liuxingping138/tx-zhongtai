#!/usr/bin/env bash
# 依赖漏洞扫描：按锁文件里的确切版本查已知漏洞。Python 用 pip-audit（PyPI 漏洞库），前端用 pnpm audit。
# 需要访问 pypi.org 与 registry.npmjs.org；漏洞库每天在变，所以不进 make check，由 pre-push 和人工定期执行。
set -euo pipefail
cd "$(dirname "$0")/.."

PY_PACKAGES="packages/platform-common services/iam-service services/audit-service services/codebook-service services/policy-service services/ai-service services/tender-service"
requirements="$(mktemp)"
trap 'rm -f "$requirements"' EXIT
failed=0

for pkg in $PY_PACKAGES; do
  echo "-- $pkg --"
  # platform-common 以本地路径依赖出现（-e ../../...），它本身单独扫描。
  (cd "$pkg" && uv export --frozen --format requirements-txt --no-emit-project --all-extras --quiet) \
    | grep -v '^-e ' > "$requirements"
  uvx --quiet pip-audit --requirement "$requirements" --require-hashes --disable-pip --progress-spinner off || failed=1
done

echo "-- frontend --"
(cd frontend && pnpm audit) || failed=1

if [ "$failed" -ne 0 ]; then
  echo "发现已知漏洞：升级到报告里的修复版本，改 pyproject / package.json 的约束后重新锁定。" >&2
  exit 1
fi
