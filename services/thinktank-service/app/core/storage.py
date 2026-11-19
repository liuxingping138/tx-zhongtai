"""智库文件安全存储：支持本地目录与 MinIO（S3v4 HTTP 协议），保留原服务器对象键约定。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlparse

import httpx
from platform_common.logging_setup import get_logger

logger = get_logger(__name__)

ALLOWED_SUFFIXES: frozenset[str] = frozenset({"PDF", "XLS", "XLSX", "DOC", "DOCX", "PPT", "PPTX", "TXT", "CSV", "MD"})

_MIME_MAP: dict[str, str] = {
    "PDF": "application/pdf",
    "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "XLS": "application/vnd.ms-excel",
    "DOCX": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "DOC": "application/msword",
    "PPTX": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "PPT": "application/vnd.ms-powerpoint",
    "TXT": "text/plain; charset=utf-8",
    "MD": "text/markdown; charset=utf-8",
    "CSV": "text/csv; charset=utf-8",
}


class StorageSettings(Protocol):
    storage_dir: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_region: str
    minio_timeout_seconds: float


def normalize_suffix(filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".").upper()
    if ext in {"XLS", "XLSX"}:
        return "EXCEL"
    if ext in {"DOC", "DOCX"}:
        return "WORD"
    if ext in {"PPT", "PPTX"}:
        return "PPT"
    return ext


def raw_extension(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").upper()


def media_type_for_file(filename: str, suffix: str) -> str:
    ext = raw_extension(filename) or suffix.upper()
    if ext == "EXCEL":
        ext = "XLSX"
    elif ext == "WORD":
        ext = "DOCX"
    return _MIME_MAP.get(ext, "application/octet-stream")


_HTTP_NOT_FOUND = 404
_HTTP_DELETE_OK = frozenset({200, 204, 404})
_storage_client: httpx.AsyncClient | None = None


class StorageUnavailableError(RuntimeError):
    """对象存储（MinIO）请求失败或超时。"""


def _build_timeout(settings: StorageSettings) -> httpx.Timeout:
    connect = float(getattr(settings, "minio_timeout_seconds", 5.0) or 5.0)
    io_timeout = float(getattr(settings, "minio_io_timeout_seconds", max(connect, 60.0)) or max(connect, 60.0))
    return httpx.Timeout(connect=connect, read=io_timeout, write=io_timeout, pool=5.0)


def _get_storage_client() -> httpx.AsyncClient:
    global _storage_client  # noqa: PLW0603  进程级连接池复用，lifespan 关闭时释放
    if _storage_client is None or _storage_client.is_closed:
        _storage_client = httpx.AsyncClient(limits=httpx.Limits(max_connections=32, max_keepalive_connections=16))
    return _storage_client


async def close_storage_client() -> None:
    global _storage_client  # noqa: PLW0603  lifespan 关闭时释放进程级连接池
    if _storage_client is not None and not _storage_client.is_closed:
        await _storage_client.aclose()
    _storage_client = None


def legacy_object_key(filename: str, size_bytes: int, ext_lower: str) -> str:
    """与原系统保持一致的 MinIO 对象键规则：`knowledgeBase/{md5Base64}.{ext}`。"""

    digest = hashlib.md5(f"{filename}/{size_bytes}/{ext_lower}".encode(), usedforsecurity=False).digest()
    file_id = base64.b64encode(digest).decode("ascii")
    return f"knowledgeBase/{file_id}.{ext_lower}"


def new_object_key(file_id: uuid.UUID, ext_lower: str) -> str:
    """新上传文件使用记录 UUID 作为对象键前缀，避免同名同大小文件键冲突与覆盖原系统文件。"""

    return f"knowledgeBase/{file_id.hex}.{ext_lower}"


def is_managed_object_key(rel_path: str, file_id: uuid.UUID) -> bool:
    """仅当对象键由本系统按记录 UUID 生成时才允许物理删除，保护迁移来的原服务器 MinIO 文件。"""

    if not rel_path:
        return False
    return rel_path.startswith(f"knowledgeBase/{file_id.hex}.") or rel_path.startswith(f"knowledgeBase/{file_id}.")


def _resolve_safe_path(base_dir: str, rel_path: str) -> Path:
    if not rel_path or Path(rel_path).is_absolute():
        raise ValueError("非法存储路径")
    root = Path(base_dir).resolve()
    target = (root / rel_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError("非法存储路径")
    return target


def _sign_s3_headers(
    settings: StorageSettings,
    method: str,
    object_key: str,
    *,
    payload: bytes = b"",
    content_type: str | None = None,
) -> tuple[str, dict[str, str]]:
    parsed = urlparse(settings.minio_endpoint.rstrip("/"))
    amz_date = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    date_stamp = amz_date[:8]
    encoded_key = quote(object_key.lstrip("/"), safe="/-_.~")
    base_path = parsed.path.rstrip("/")
    canonical_uri = f"{base_path}/{settings.minio_bucket}/{encoded_key}"
    payload_hash = hashlib.sha256(payload).hexdigest()

    sign_headers: dict[str, str] = {
        "host": parsed.netloc,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        sign_headers["content-type"] = content_type
    sorted_keys = sorted(sign_headers)
    canonical_headers = "".join(f"{k}:{sign_headers[k].strip()}\n" for k in sorted_keys)
    signed_headers = ";".join(sorted_keys)
    canonical_req = f"{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    scope = f"{date_stamp}/{settings.minio_region}/s3/aws4_request"
    string_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{hashlib.sha256(canonical_req.encode()).hexdigest()}"

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    signing_key = _hmac(
        _hmac(_hmac(_hmac(f"AWS4{settings.minio_secret_key}".encode(), date_stamp), settings.minio_region), "s3"),
        "aws4_request",
    )
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    auth = (
        f"AWS4-HMAC-SHA256 Credential={settings.minio_access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    url = f"{parsed.scheme}://{parsed.netloc}{canonical_uri}"
    out_headers = {
        "Authorization": auth,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        out_headers["Content-Type"] = content_type
    return url, out_headers


def _use_minio(settings: StorageSettings | None) -> bool:
    if settings is None:
        return False
    ep = str(getattr(settings, "minio_endpoint", "") or "").strip()
    bucket = str(getattr(settings, "minio_bucket", "") or "").strip()
    return bool(ep and bucket)


async def save_bytes(base_dir: str, rel_path: str, content: bytes) -> None:
    target = _resolve_safe_path(base_dir, rel_path)

    def _write() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    await asyncio.to_thread(_write)


async def read_bytes(base_dir: str, rel_path: str) -> bytes | None:
    if not rel_path:
        return None
    target = _resolve_safe_path(base_dir, rel_path)

    def _read() -> bytes | None:
        if not target.is_file():
            return None
        return target.read_bytes()

    return await asyncio.to_thread(_read)


async def delete_file(base_dir: str, rel_path: str) -> None:
    if not rel_path:
        return
    target = _resolve_safe_path(base_dir, rel_path)

    def _unlink() -> None:
        if target.is_file():
            target.unlink()

    await asyncio.to_thread(_unlink)


async def save_object(
    settings: StorageSettings,
    rel_path: str,
    content: bytes,
    *,
    content_type: str = "application/octet-stream",
) -> None:
    _resolve_safe_path(settings.storage_dir, rel_path)
    if _use_minio(settings):
        url, headers = _sign_s3_headers(settings, "PUT", rel_path, payload=content, content_type=content_type)
        try:
            resp = await _get_storage_client().put(
                url, content=content, headers=headers, timeout=_build_timeout(settings)
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("minio_save_failed", path=rel_path, error=str(exc))
            raise StorageUnavailableError(f"对象存储写入失败：{exc}") from exc
        return
    await save_bytes(settings.storage_dir, rel_path, content)


async def read_object(
    settings: StorageSettings,
    rel_path: str,
    *,
    raise_on_error: bool = False,
) -> bytes | None:
    if not rel_path:
        return None
    _resolve_safe_path(settings.storage_dir, rel_path)
    minio_error: httpx.HTTPError | None = None
    if _use_minio(settings):
        url, headers = _sign_s3_headers(settings, "GET", rel_path)
        try:
            resp = await _get_storage_client().get(url, headers=headers, timeout=_build_timeout(settings))
            if resp.status_code == _HTTP_NOT_FOUND:
                return None
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as exc:
            minio_error = exc
            logger.warning("minio_read_fallback", path=rel_path, error=str(exc))
    local = await read_bytes(settings.storage_dir, rel_path)
    if local is not None:
        return local
    if minio_error is not None and raise_on_error:
        raise StorageUnavailableError(f"对象存储读取失败：{minio_error}") from minio_error
    return None


async def _iter_local_chunks(target: Path, chunk_size: int) -> AsyncIterator[bytes]:
    with target.open("rb") as fp:
        while chunk := await asyncio.to_thread(fp.read, chunk_size):
            yield chunk


async def _iter_minio_chunks(resp: httpx.Response, chunk_size: int, rel_path: str) -> AsyncIterator[bytes]:
    try:
        async for chunk in resp.aiter_bytes(chunk_size):
            if chunk:
                yield chunk
    except httpx.HTTPError as exc:
        logger.warning("minio_stream_failed", path=rel_path, error=str(exc))
        raise StorageUnavailableError(f"对象存储流式读取失败：{exc}") from exc
    finally:
        await resp.aclose()


async def stream_object(
    settings: StorageSettings,
    rel_path: str,
    *,
    chunk_size: int = 65536,
) -> tuple[AsyncIterator[bytes], int | None] | None:
    if not rel_path:
        return None
    target = _resolve_safe_path(settings.storage_dir, rel_path)
    minio_error: httpx.HTTPError | None = None
    if _use_minio(settings):
        url, headers = _sign_s3_headers(settings, "GET", rel_path)
        client = _get_storage_client()
        try:
            req = client.build_request("GET", url, headers=headers, timeout=_build_timeout(settings))
            resp = await client.send(req, stream=True)
            if resp.status_code == _HTTP_NOT_FOUND:
                await resp.aclose()
                return None
            if resp.status_code >= httpx.codes.BAD_REQUEST:
                await resp.aclose()
                resp.raise_for_status()
            raw_len = resp.headers.get("content-length")
            size = int(raw_len) if raw_len and raw_len.isdigit() else None
            return _iter_minio_chunks(resp, chunk_size, rel_path), size
        except httpx.HTTPError as exc:
            minio_error = exc
            logger.warning("minio_stream_fallback", path=rel_path, error=str(exc))
    if target.is_file():
        return _iter_local_chunks(target, chunk_size), target.stat().st_size
    if minio_error is not None:
        raise StorageUnavailableError(f"对象存储读取失败：{minio_error}") from minio_error
    return None


async def delete_object(settings: StorageSettings, rel_path: str) -> None:
    if not rel_path:
        return
    _resolve_safe_path(settings.storage_dir, rel_path)
    if _use_minio(settings):
        url, headers = _sign_s3_headers(settings, "DELETE", rel_path)
        try:
            resp = await _get_storage_client().delete(url, headers=headers, timeout=_build_timeout(settings))
            if resp.status_code not in _HTTP_DELETE_OK:
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("minio_delete_failed", path=rel_path, error=str(exc))
            raise StorageUnavailableError(f"对象存储删除失败：{exc}") from exc
        return
    await delete_file(settings.storage_dir, rel_path)
