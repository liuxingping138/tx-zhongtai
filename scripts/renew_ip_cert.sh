#!/usr/bin/env bash
# Certbot >=5.4 支持短期 IP 证书。用 standalone 模式：校验那几秒 certbot 临时监听宿主机 80，所以 80 必须空着。
set -euo pipefail
umask 077
: "${PUBLIC_IP:?请设置 PUBLIC_IP}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/ip_cert_lib.sh
. "$ROOT/scripts/ip_cert_lib.sh"
DEST="${CERT_DIR:-$ROOT/deploy/secrets/tls}"
STATE="${ACME_STATE_DIR:-/var/lib/tx-zhongtai-acme}"
HTTPS_PORT="${HTTPS_PORT:-8443}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-tx-zhongtai-gateway-1}"
# Traefik 收到配置变化后默认先等 2 秒（providersThrottleDuration）再生效，热加载最多等这么久才算失败、去重启网关。
RELOAD_WAIT_SECONDS="${RELOAD_WAIT_SECONDS:-20}"
RESTART_WAIT_SECONDS="${RESTART_WAIT_SECONDS:-40}"
GATEWAY_DYNAMIC="$ROOT/deploy/gateway/dynamic.https.yml"
mkdir -p "$DEST" "$STATE"
chmod 700 "$DEST" "$STATE"
exec 9>"$STATE/renew.lock"
flock -n 9 || exit 0
# 中途失败（校验不过、磁盘满）不留下 .next 半成品
trap 'rm -f "$DEST/fullchain.pem.next" "$DEST/privkey.pem.next" "$GATEWAY_DYNAMIC.next"' EXIT
CERTBOT_IMAGE="${CERTBOT_IMAGE:-certbot/certbot:v5.4.0}"
email_args=(--register-unsafely-without-email)
if [ -n "${ACME_EMAIL:-}" ]; then email_args=(-m "$ACME_EMAIL"); fi
docker run --rm -v "$STATE:/etc/letsencrypt" -p 80:80 "$CERTBOT_IMAGE" \
  certonly --non-interactive --agree-tos --preferred-profile shortlived \
  --standalone --ip-address "$PUBLIC_IP" \
  --cert-name tx-zhongtai-ip "${email_args[@]}" --keep-until-expiring
src="$STATE/live/tx-zhongtai-ip"

# 发布前校验：能解析、没过期、包含本机 IP、私钥和证书是一对。
# 不合格的不发布：换上去 Traefik 加载失败就改发自签证书，HTTPS 一直断到有人手工处理；不换的话旧证书还能撑几天。
validate_new_cert() {
  local cert="$1" key="$2"
  if ! openssl x509 -in "$cert" -noout >/dev/null 2>&1; then
    echo "错误：$cert 不是合法的 PEM 证书，未发布" >&2
    return 1
  fi
  if ! openssl pkey -in "$key" -noout >/dev/null 2>&1; then
    echo "错误：$key 不是合法的 PEM 私钥，未发布" >&2
    return 1
  fi
  if ! openssl x509 -in "$cert" -noout -checkend 0 >/dev/null; then
    echo "错误：$cert 已过期，未发布" >&2
    return 1
  fi
  if ! cert_covers_ip "$cert" "$PUBLIC_IP"; then
    echo "错误：$cert 不包含 IP $PUBLIC_IP，未发布" >&2
    return 1
  fi
  if ! cert_key_match "$cert" "$key"; then
    echo "错误：$key 和 $cert 不是一对（公钥不一致），未发布" >&2
    return 1
  fi
}

# 只有证书发生变化才发布；校验通过后同目录 rename，避免 Traefik 读到半截或空文件。
if ! cmp -s "$src/fullchain.pem" "$DEST/fullchain.pem" || ! cmp -s "$src/privkey.pem" "$DEST/privkey.pem"; then
  validate_new_cert "$src/fullchain.pem" "$src/privkey.pem"
  install -m 644 "$src/fullchain.pem" "$DEST/fullchain.pem.next"
  install -m 600 "$src/privkey.pem" "$DEST/privkey.pem.next"
  mv "$DEST/privkey.pem.next" "$DEST/privkey.pem"
  mv "$DEST/fullchain.pem.next" "$DEST/fullchain.pem"
  sync
  # 网关挂载整个配置目录，原子替换配置触发 file Provider 重新读取证书。
  install -m 644 "$GATEWAY_DYNAMIC" "$GATEWAY_DYNAMIC.next"
  mv "$GATEWAY_DYNAMIC.next" "$GATEWAY_DYNAMIC"
  # 网关实际下发的必须就是新证书：只看握手不够，Traefik 加载失败时改发自带的自签证书，握手照样成功。
  # 轮询等热加载生效，等不到再重启：重启会断开所有连接（流式回答、大文件下载），不能因为多等了一秒就重启。
  if ! container_running "$GATEWAY_CONTAINER"; then
    echo "警告：网关容器 $GATEWAY_CONTAINER 没在运行，没有核对网关下发的证书（新证书已发布，网关起来后由每日巡检核对）" >&2
  elif ! wait_until_served "$HTTPS_PORT" "$RELOAD_WAIT_SECONDS" "$DEST/fullchain.pem"; then
    echo "警告：网关 ${RELOAD_WAIT_SECONDS} 秒内没有换上新证书，正在重启 $GATEWAY_CONTAINER…" >&2
    docker restart "$GATEWAY_CONTAINER" >/dev/null
    if ! wait_until_served "$HTTPS_PORT" "$RESTART_WAIT_SECONDS" "$DEST/fullchain.pem"; then
      echo "错误：重启 $GATEWAY_CONTAINER 后 ${RESTART_WAIT_SECONDS} 秒内网关下发的仍不是新证书" >&2
      exit 1
    fi
  fi
fi
openssl x509 -in "$DEST/fullchain.pem" -noout -dates
