#!/usr/bin/env bash
# Certbot >=5.4 的 webroot 模式支持短期 IP 证书；不占用或重启宿主机 Web 服务。
set -euo pipefail
umask 077
: "${PUBLIC_IP:?请设置 PUBLIC_IP}"
: "${ACME_WEBROOT:?请设置已有 HTTP 站点的 ACME_WEBROOT}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${CERT_DIR:-$ROOT/deploy/secrets/tls}"
STATE="${ACME_STATE_DIR:-/var/lib/tx-zhongtai-acme}"
mkdir -p "$DEST" "$STATE" "$ACME_WEBROOT/.well-known/acme-challenge"
# 校验目录必须允许现有 Nginx worker 读取；私钥目录保持 700。
chmod 755 "$ACME_WEBROOT/.well-known" "$ACME_WEBROOT/.well-known/acme-challenge"
chmod 700 "$DEST" "$STATE"
exec 9>"$STATE/renew.lock"
flock -n 9 || exit 0
CERTBOT_IMAGE="${CERTBOT_IMAGE:-certbot/certbot:v5.4.0}"
email_args=(--register-unsafely-without-email)
if [ -n "${ACME_EMAIL:-}" ]; then email_args=(-m "$ACME_EMAIL"); fi
docker run --rm -v "$STATE:/etc/letsencrypt" -v "$ACME_WEBROOT:/webroot" "$CERTBOT_IMAGE" \
  certonly --non-interactive --agree-tos --preferred-profile shortlived \
  --webroot --webroot-path /webroot --ip-address "$PUBLIC_IP" \
  --cert-name tx-zhongtai-ip "${email_args[@]}" --keep-until-expiring
src="$STATE/live/tx-zhongtai-ip"
# 只有证书发生变化才发布；同目录 rename 避免读取写到一半的文件。
if ! cmp -s "$src/fullchain.pem" "$DEST/fullchain.pem" || ! cmp -s "$src/privkey.pem" "$DEST/privkey.pem"; then
  install -m 644 "$src/fullchain.pem" "$DEST/fullchain.pem.next"
  install -m 600 "$src/privkey.pem" "$DEST/privkey.pem.next"
  mv "$DEST/privkey.pem.next" "$DEST/privkey.pem"
  mv "$DEST/fullchain.pem.next" "$DEST/fullchain.pem"
  # 网关挂载整个配置目录，原子替换配置触发 file Provider 重新读取证书。
  install -m 644 "$ROOT/deploy/gateway/dynamic.https.yml" "$ROOT/deploy/gateway/dynamic.https.yml.next"
  mv "$ROOT/deploy/gateway/dynamic.https.yml.next" "$ROOT/deploy/gateway/dynamic.https.yml"
fi
openssl x509 -in "$DEST/fullchain.pem" -noout -dates
