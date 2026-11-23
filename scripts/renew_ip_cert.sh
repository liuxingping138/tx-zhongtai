#!/usr/bin/env bash
# Certbot >=5.4 支持短期 IP 证书。用 standalone 模式：校验那几秒 certbot 临时监听宿主机 80，所以 80 必须空着。
set -euo pipefail
umask 077
: "${PUBLIC_IP:?请设置 PUBLIC_IP}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${CERT_DIR:-$ROOT/deploy/secrets/tls}"
STATE="${ACME_STATE_DIR:-/var/lib/tx-zhongtai-acme}"
HTTPS_PORT="${HTTPS_PORT:-8443}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-tx-zhongtai-gateway-1}"
mkdir -p "$DEST" "$STATE"
chmod 700 "$DEST" "$STATE"
exec 9>"$STATE/renew.lock"
flock -n 9 || exit 0
CERTBOT_IMAGE="${CERTBOT_IMAGE:-certbot/certbot:v5.4.0}"
email_args=(--register-unsafely-without-email)
if [ -n "${ACME_EMAIL:-}" ]; then email_args=(-m "$ACME_EMAIL"); fi
docker run --rm -v "$STATE:/etc/letsencrypt" -p 80:80 "$CERTBOT_IMAGE" \
  certonly --non-interactive --agree-tos --preferred-profile shortlived \
  --standalone --ip-address "$PUBLIC_IP" \
  --cert-name tx-zhongtai-ip "${email_args[@]}" --keep-until-expiring
src="$STATE/live/tx-zhongtai-ip"

verify_https() {
  curl -sk --max-time 5 -o /dev/null "https://127.0.0.1:${HTTPS_PORT}/"
}

# 只有证书发生变化才发布；先校验 PEM 合法非空，再同目录 rename 避免 Traefik 读到半截或空文件。
if ! cmp -s "$src/fullchain.pem" "$DEST/fullchain.pem" || ! cmp -s "$src/privkey.pem" "$DEST/privkey.pem"; then
  openssl x509 -in "$src/fullchain.pem" -noout >/dev/null
  openssl pkey -in "$src/privkey.pem" -noout >/dev/null
  install -m 644 "$src/fullchain.pem" "$DEST/fullchain.pem.next"
  install -m 600 "$src/privkey.pem" "$DEST/privkey.pem.next"
  mv "$DEST/privkey.pem.next" "$DEST/privkey.pem"
  mv "$DEST/fullchain.pem.next" "$DEST/fullchain.pem"
  sync
  # 网关挂载整个配置目录，原子替换配置触发 file Provider 重新读取证书。
  install -m 644 "$ROOT/deploy/gateway/dynamic.https.yml" "$ROOT/deploy/gateway/dynamic.https.yml.next"
  mv "$ROOT/deploy/gateway/dynamic.https.yml.next" "$ROOT/deploy/gateway/dynamic.https.yml"
  # 校验网关热加载后的实际 HTTPS 握手；若 Traefik 重载异常则自动重启网关兜底。
  sleep 2
  if docker ps --format '{{.Names}}' | grep -qx "$GATEWAY_CONTAINER" && ! verify_https; then
    echo "警告：网关热加载证书后 HTTPS 握手失败，正在重启 $GATEWAY_CONTAINER…" >&2
    docker restart "$GATEWAY_CONTAINER" >/dev/null
    sleep 2
    verify_https
  fi
fi
openssl x509 -in "$DEST/fullchain.pem" -noout -dates
