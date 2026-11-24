# shellcheck shell=bash
# renew_ip_cert.sh 和 check_ip_cert_expiry.sh 共用的证书检查（由它们 source，不单独执行）。
#
# 生产机是 CentOS 7，自带 OpenSSL 1.0.2k-fips，两处和新版本不一样，这里都按它写：
# - `openssl x509 -checkip` 不论对不对都退出 0，只能看输出（"does match certificate" / "does NOT match certificate"）；
# - 没有 `sha256` 命令，摘要一律用 `openssl dgst -sha256`（两边同一个 openssl，输出格式一致，可以直接比）。

# 证书文件里第一张（叶子）证书的 SHA-256 指纹。
cert_file_fingerprint() {
  openssl x509 -in "$1" -noout -fingerprint -sha256
}

# 网关在 127.0.0.1:<端口> 实际下发的叶子证书指纹；连不上、握手失败输出空串。
# 不带 SNI：浏览器按 IP 访问时也不发 SNI，Traefik 下发的是 tls.stores.default.defaultCertificate。
served_fingerprint() {
  timeout 10 openssl s_client -connect "127.0.0.1:$1" </dev/null 2>/dev/null \
    | openssl x509 -noout -fingerprint -sha256 2>/dev/null || true
}

# 网关下发的就是这张证书文件。
gateway_serves() {
  local want got
  want="$(cert_file_fingerprint "$2")" || return 1
  got="$(served_fingerprint "$1")"
  [ -n "$got" ] && [ "$got" = "$want" ]
}

# 证书和私钥是一对：比公钥的摘要。先确认两边都真的取出了公钥，
# 否则两边都失败时是两个空串的摘要，会误判成一对。
cert_key_match() {
  local cert_pub key_pub
  cert_pub="$(openssl x509 -in "$1" -noout -pubkey 2>/dev/null)" || return 1
  key_pub="$(openssl pkey -in "$2" -pubout 2>/dev/null)" || return 1
  case "$cert_pub" in *"BEGIN PUBLIC KEY"*) ;; *) return 1 ;; esac
  case "$key_pub" in *"BEGIN PUBLIC KEY"*) ;; *) return 1 ;; esac
  [ "$(printf '%s\n' "$cert_pub" | openssl dgst -sha256)" = "$(printf '%s\n' "$key_pub" | openssl dgst -sha256)" ]
}

# 证书包含这个 IP。OpenSSL 1.0.2k 的 -checkip 不对也退出 0，所以只认输出，不看退出码。
cert_covers_ip() {
  local out
  out="$(openssl x509 -in "$1" -noout -checkip "$2" 2>&1 || true)"
  printf '%s\n' "$out" | grep -q "does match certificate"
}

# 网关容器在运行。
container_running() {
  [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" = "true" ]
}

# 最多等 $2 秒，直到网关（端口 $1）下发证书文件 $3；每秒看一次。
wait_until_served() {
  local deadline=$((SECONDS + $2))
  until gateway_serves "$1" "$3"; do
    [ "$SECONDS" -ge "$deadline" ] && return 1
    sleep 1
  done
}
