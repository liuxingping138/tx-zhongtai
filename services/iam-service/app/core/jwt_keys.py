"""RSA JWT 密钥与 JWKS。

密钥文件存放在 `IAM_JWT_KEYS_DIR`，不进入仓库。目录为空时在开发/测试环境
自动生成一把当前密钥；生产环境缺失密钥则拒绝启动。
"""

from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt.algorithms import RSAAlgorithm

_CURRENT_NAME = "current.json"
_PRIVATE_SUFFIX = ".pem"
_PUBLIC_SUFFIX = ".pub"


class JwtKeyError(RuntimeError):
    pass


def _write_keypair(directory: Path, kid: str) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    (directory / f"{kid}{_PRIVATE_SUFFIX}").write_bytes(private_pem)
    (directory / f"{kid}{_PUBLIC_SUFFIX}").write_bytes(public_pem)
    (directory / f"{kid}{_PRIVATE_SUFFIX}").chmod(0o600)


def ensure_jwt_keys(directory: Path, *, allow_generate: bool) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    current_path = directory / _CURRENT_NAME
    if current_path.exists():
        return json.loads(current_path.read_text(encoding="utf-8"))
    if not allow_generate:
        raise JwtKeyError(f"JWT 密钥目录为空且不允许自动生成: {directory}")
    kid = "k1"
    _write_keypair(directory, kid)
    meta = {"current_kid": kid, "previous_kid": None}
    current_path.write_text(json.dumps(meta), encoding="utf-8")
    return meta


def load_private_pem(directory: Path, kid: str) -> bytes:
    path = directory / f"{kid}{_PRIVATE_SUFFIX}"
    if not path.exists():
        raise JwtKeyError(f"缺少私钥 kid={kid}")
    return path.read_bytes()


def load_public_pem(directory: Path, kid: str) -> bytes:
    path = directory / f"{kid}{_PUBLIC_SUFFIX}"
    if not path.exists():
        raise JwtKeyError(f"缺少公钥 kid={kid}")
    return path.read_bytes()


def build_jwks(directory: Path, meta: dict) -> dict:
    kids = [meta["current_kid"]]
    if meta.get("previous_kid"):
        kids.append(meta["previous_kid"])
    keys = []
    for kid in kids:
        public_pem = load_public_pem(directory, kid)
        public_key = serialization.load_pem_public_key(public_pem)
        if not isinstance(public_key, RSAPublicKey):
            raise JwtKeyError(f"公钥不是 RSA kid={kid}")
        jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
        jwk["kid"] = kid
        jwk["use"] = "sig"
        jwk["alg"] = "RS256"
        keys.append(jwk)
    return {"keys": keys}
