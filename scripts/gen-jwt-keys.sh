#!/usr/bin/env bash
# 生成 iam-service 可读的 JWT 密钥（格式同 app/core/jwt_keys.py：PKCS8 私钥 + SPKI 公钥 + current.json）。
# 只用 openssl，Mac 和服务器都不需要装 uv。目录里已有 current.json 时什么都不做。
# 用部署用户（而不是 sudo）执行：容器里的 appuser 与部署用户同为 uid 1000，私钥 600 也能读到。
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
echo "已生成 JWT 密钥: $dir"
