#!/usr/bin/env bash
# 从本地应用对象重新导出 OpenAPI，并与 docs/openapi 比较。不一致则失败。
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export OPENAPI_OUT="$tmp"
(
  cd "$root/services/iam-service"
  uv run python ../../scripts/export_openapi.py iam
)
(
  cd "$root/services/audit-service"
  uv run python ../../scripts/export_openapi.py audit
)
(
  cd "$root/services/codebook-service"
  uv run python ../../scripts/export_openapi.py codebook
)
(
  cd "$root/services/policy-service"
  uv run python ../../scripts/export_openapi.py policy
)
(
  cd "$root/services/ai-service"
  uv run python ../../scripts/export_openapi.py ai
)
(
  cd "$root/services/tender-service"
  uv run python ../../scripts/export_openapi.py tender
)
diff -ru "$root/docs/openapi" "$tmp"
echo "openapi_matches_apps"
