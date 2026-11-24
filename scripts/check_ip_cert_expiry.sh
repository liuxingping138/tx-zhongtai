#!/usr/bin/env bash
# 检查服务器 TLS 证书是否即将在 48 小时内过期、私钥是不是和它一对、（设了 PUBLIC_IP 时）是否包含本机 IP，
# 并验证网关实际下发的就是这张证书。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/ip_cert_lib.sh
. "$ROOT/scripts/ip_cert_lib.sh"

CERT_PATH="${1:-${CERT_PATH:-/data/tx-zhongtai/deploy/secrets/tls/fullchain.pem}}"
KEY_PATH="${KEY_PATH:-$(dirname "$CERT_PATH")/privkey.pem}"
MIN_SECONDS="${MIN_SECONDS:-172800}"
HTTPS_PORT="${HTTPS_PORT:-8443}"
CHECK_GATEWAY="${CHECK_GATEWAY:-1}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-tx-zhongtai-gateway-1}"

if [ ! -f "$CERT_PATH" ]; then
  echo "证书文件不存在: $CERT_PATH" >&2
  exit 2
fi

if ! openssl x509 -in "$CERT_PATH" -noout -checkend "$MIN_SECONDS"; then
  echo "警告：证书将在 $((MIN_SECONDS / 3600)) 小时内过期: $CERT_PATH" >&2
  exit 1
fi

if [ -r "$KEY_PATH" ] && ! cert_key_match "$CERT_PATH" "$KEY_PATH"; then
  echo "警告：$KEY_PATH 和 $CERT_PATH 不是一对（公钥不一致），网关加载不了这张证书" >&2
  exit 5
fi

# 巡检单元默认不带 PUBLIC_IP（只有续期单元读 /etc/tx-zhongtai-acme.env），设了才查。
if [ -n "${PUBLIC_IP:-}" ] && ! cert_covers_ip "$CERT_PATH" "$PUBLIC_IP"; then
  echo "警告：$CERT_PATH 不包含 IP $PUBLIC_IP" >&2
  exit 6
fi

if [ "$CHECK_GATEWAY" = "1" ]; then
  # 只看握手成不成功不够：Traefik 加载证书失败时改发自带的自签证书，握手照样成功。
  got="$(served_fingerprint "$HTTPS_PORT")"
  if [ -z "$got" ]; then
    hint=""
    if command -v docker >/dev/null 2>&1 && ! container_running "$GATEWAY_CONTAINER"; then
      hint="（网关容器 $GATEWAY_CONTAINER 没在运行）"
    fi
    echo "警告：网关 https://127.0.0.1:${HTTPS_PORT}/ TLS 握手失败${hint}" >&2
    exit 3
  fi
  if [ "$got" != "$(cert_file_fingerprint "$CERT_PATH")" ]; then
    echo "警告：网关下发的证书不是 $CERT_PATH（可能是 Traefik 自签证书或旧证书）" >&2
    exit 4
  fi
fi

echo "证书有效期正常，网关下发的就是这张证书: $CERT_PATH"
