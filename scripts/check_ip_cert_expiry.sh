#!/usr/bin/env bash
# 检查服务器 TLS 证书是否即将在 48 小时内过期。
set -euo pipefail

CERT_PATH="${1:-${CERT_PATH:-/data/tx-zhongtai/deploy/secrets/tls/fullchain.pem}}"
MIN_SECONDS="${MIN_SECONDS:-172800}"

if [ ! -f "$CERT_PATH" ]; then
  echo "证书文件不存在: $CERT_PATH" >&2
  exit 2
fi

if ! openssl x509 -in "$CERT_PATH" -noout -checkend "$MIN_SECONDS"; then
  echo "警告：证书将在 $((MIN_SECONDS / 3600)) 小时内过期: $CERT_PATH" >&2
  exit 1
fi
echo "证书有效期正常: $CERT_PATH"
