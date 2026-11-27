"""从码表服务实时拉取智库 6 张专属码表（/internal/v1/thinktank-dicts），仅异常不可达时短时熔断回退。"""

from __future__ import annotations

import time
from typing import Any, Protocol

import httpx
from platform_common.internal_calls import internal_headers
from platform_common.logging_setup import get_logger

logger = get_logger(__name__)

# 正常调用不缓存，码表变更后智库立即生效；仅在码表服务异常不可达时短时熔断，避免雪崩阻塞。
_FAIL_BACKOFF_SECONDS = 10.0
_fail_until: dict[str, float] = {}
_last_good: dict[str, dict[str, list[str]]] = {}
_HTTP_LIMITS = httpx.Limits(max_keepalive_connections=10, max_connections=20)
_client: httpx.AsyncClient | None = None
_client_factory: Any = None

DEFAULT_THINKTANK_DICTS: dict[str, tuple[str, ...]] = {
    "file_types": (
        "经分",
        "通报",
        "工作会",
        "行业营销指引",
        "工作部署&专项行动",
        "网络规划",
        "考核",
        "产品",
        "政企改革&数字化",
        "客户视图",
        "通知",
        "渠道&生态",
        "国际业务",
        "其他",
    ),
    "departments": (
        "政企部",
        "市场部",
        "工业行业事业部",
        "公众客户销售中心",
        "国际部",
        "集团商业客户拓展部",
        "集团政企应急行业事业部",
        "交通物流行业事业部",
        "柯瑞文董事长",
    ),
    "industries": (
        "党政",
        "工业能源",
        "教育",
        "医卫",
        "交通物流",
        "IT互联网",
        "金融",
        "农业",
        "住建",
        "文旅",
        "中小",
        "无",
    ),
    "product_types": (
        "云",
        "网",
        "数",
        "智",
        "安",
        "语音",
        "消息",
        "数字平台",
        "量子",
        "解决方案",
        "服务",
        "无",
    ),
    "provinces": (
        "集团",
        "北京市",
        "天津市",
        "河北省",
        "山西省",
        "内蒙古自治区",
        "辽宁省",
        "吉林省",
        "黑龙江省",
        "上海市",
        "江苏省",
        "浙江省",
        "安徽省",
        "福建省",
        "江西省",
        "山东省",
        "河南省",
        "湖北省",
        "湖南省",
        "广东省",
        "广西壮族自治区",
        "海南省",
        "重庆市",
        "四川省",
        "贵州省",
        "云南省",
        "西藏自治区",
        "陕西省",
        "甘肃省",
        "青海省",
        "宁夏回族自治区",
        "新疆维吾尔自治区",
    ),
    "market_categories": ("行客", "商客", "综合", "无"),
}


def _get_client() -> httpx.AsyncClient:
    global _client, _client_factory  # noqa: PLW0603  进程级连接池复用，lifespan 关闭时释放
    if _client is None or _client.is_closed or _client_factory is not httpx.AsyncClient:
        _client = httpx.AsyncClient(limits=_HTTP_LIMITS)
        _client_factory = httpx.AsyncClient
    return _client


async def close_codebook_client() -> None:
    global _client, _client_factory  # noqa: PLW0603  lifespan 关闭时释放进程级 HTTP 连接池
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
    _client_factory = None


class CodebookSettings(Protocol):
    codebook_base_url: str
    codebook_service_secret: str
    codebook_timeout_seconds: float


def clear_thinktank_dicts_cache() -> None:
    _fail_until.clear()
    _last_good.clear()


def default_thinktank_dicts() -> dict[str, list[str]]:
    return {key: list(values) for key, values in DEFAULT_THINKTANK_DICTS.items()}


def _copy_dicts(source: dict[str, list[str]]) -> dict[str, list[str]]:
    return {key: list(values) for key, values in source.items()}


def _clean_items(raw: Any, fallback: tuple[str, ...]) -> list[str]:
    if not isinstance(raw, list):
        return list(fallback)
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item).strip() if item is not None else ""
        if text and text not in seen:
            seen.add(text)
            cleaned.append(text)
    return cleaned or list(fallback)


def _normalize_payload(raw_data: Any) -> dict[str, list[str]]:
    data = raw_data if isinstance(raw_data, dict) else {}
    return {key: _clean_items(data.get(key), fallback) for key, fallback in DEFAULT_THINKTANK_DICTS.items()}


async def get_thinktank_dicts(settings: CodebookSettings) -> dict[str, list[str]]:
    """实时拉取智库 6 张专属码表；未配置或字段为空时逐键回退内置默认，异常时短时熔断并优先回退最近一次成功快照。"""

    base_url = (getattr(settings, "codebook_base_url", "") or "").strip().rstrip("/")
    secret = (getattr(settings, "codebook_service_secret", "") or "").strip()
    if not base_url or not secret:
        return default_thinktank_dicts()

    now = time.monotonic()
    backoff_until = _fail_until.get(base_url, 0.0)
    if now < backoff_until:
        snapshot = _last_good.get(base_url)
        return _copy_dicts(snapshot) if snapshot is not None else default_thinktank_dicts()

    try:
        resp = await _get_client().get(
            f"{base_url}/internal/v1/thinktank-dicts",
            headers=internal_headers("thinktank-service", secret),
            timeout=settings.codebook_timeout_seconds,
        )
        resp.raise_for_status()
        payload = resp.json()
        raw_data = payload.get("data") if isinstance(payload, dict) else None
        normalized = _normalize_payload(raw_data)
        _last_good[base_url] = normalized
        _fail_until.pop(base_url, None)
        return _copy_dicts(normalized)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("codebook_thinktank_dicts_fallback", error=str(exc))
        _fail_until[base_url] = now + _FAIL_BACKOFF_SECONDS
        snapshot = _last_good.get(base_url)
        return _copy_dicts(snapshot) if snapshot is not None else default_thinktank_dicts()
