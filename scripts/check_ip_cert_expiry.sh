#!/usr/bin/env bash
# 检查服务器 TLS 证书是否即将在 48 小时内过期，并验证网关实时 HTTPS 握手可用。
set -euo pipefail

CERT_PATH="${1:-${CERT_PATH:-/data/tx-zhongtai/deploy/secrets/tls/fullchain.pem}}"
MIN_SECONDS="${MIN_SECONDS:-172800}"
HTTPS_PORT="${HTTPS_PORT:-8443}"
CHECK_GATEWAY="${CHECK_GATEWAY:-1}"

if [ ! -f "$CERT_PATH" ]; then
  echo "证书文件不存在: $CERT_PATH" >&2
  exit 2
fi

if ! openssl x509 -in "$CERT_PATH" -noout -checkend "$MIN_SECONDS"; then
  echo "警告：证书将在 $((MIN_SECONDS / 3600)) 小时内过期: $CERT_PATH" >&2
  exit 1
fi

if [ "$CHECK_GATEWAY" = "1" ]; then
  if ! curl -sk --max-time 5 -o /dev/null "https://127.0.0.1:${HTTPS_PORT}/"; then
    echo "警告：网关 https://127.0.0.1:${HTTPS_PORT}/ TLS 握手失败" >&2
    exit 3
  fi
fi

echo "证书有效期与网关 HTTPS 握手均正常: $CERT_PATH"
