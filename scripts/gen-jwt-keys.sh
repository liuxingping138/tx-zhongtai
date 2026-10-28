#!/usr/bin/env bash
# 生成 iam-service 可读的 JWT 密钥（格式同 app/core/jwt_keys.py：PKCS8 私钥 + SPKI 公钥 + current.json）。
# 只用 openssl，Mac 和服务器都不需要装 uv。目录里已有 current.json 时什么都不做。
# 容器里的 appuser 是 uid 1000，私钥 600 只有它能读：用 uid 1000 的部署用户执行，或者用 root 执行、生成后改属主。
set -euo pipefail

dir="${1:?用法: gen-jwt-keys.sh <密钥目录>}"
mkdir -p "$dir"
if [ -f "$dir/current.json" ]; then
  exit 0
fi

kid="k1"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$dir/$kid.pem" 2>/dev/null
chmod 600 "$dir/$kid.pem"
openssl pkey -in "$dir/$kid.pem" -pubout -out "$dir/$kid.pub"
printf '{"current_kid": "%s", "previous_kid": null}' "$kid" > "$dir/current.json"
if [ "$(id -u)" = 0 ]; then
  chown -R 1000:1000 "$dir"
fi
echo "已生成 JWT 密钥: $dir"
