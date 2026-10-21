"""模型配置：「模型配置」页的新增和编辑，以及提问、批量按模型 ID 取调用参数。

改完立即生效：每次提问、每个批量任务开跑时都从库里读。已在跑的批量任务用开跑时读到的配置。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_emit import enqueue_event
from app.domain.llm_models import (
    DEFAULT_PEAK_HOURS,
    PROVIDERS,
    REASONING_EFFORTS,
    SERVICE_TIERS,
    THINKING_MODES,
    LlmModel,
    parse_peak_hours,
)
from app.domain.models import AiModel
from app.repositories import model_configs as repo

# 模型 ID 会出现在模板、任务和请求参数里：中英文、数字、点、横线、下划线。
_ID = re.compile(r"[\w.\-一-鿿]{1,64}")
_PRICE_MAX = Decimal(1000)
_PRICE_PLACES = 6
_PRICE_FIELDS = (
    "input_price",
    "output_price",
    "flex_input_price",
    "flex_output_price",
    "peak_input_price",
    "peak_output_price",
    "search_price",
)
_TEXT_LIMITS = {"name": 100, "endpoint": 128, "rate_limit": 500}


def _invalid(message: str) -> ApiError:
    return ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)


def to_model(row: AiModel) -> LlmModel:
    return LlmModel(
        id=row.id,
        name=row.name,
        provider=row.provider,
        model=row.endpoint,
        web_search=row.web_search,
        thinking=row.thinking,
        reasoning_effort=row.reasoning_effort,
        service_tier=row.service_tier,
        input_price=row.input_price,
        output_price=row.output_price,
        flex_input_price=row.flex_input_price,
        flex_output_price=row.flex_output_price,
        peak_input_price=row.peak_input_price,
        peak_output_price=row.peak_output_price,
        peak_hours=row.peak_hours,
        search_price=row.search_price,
    )


def _price_text(value: Decimal | None) -> str:
    return "" if value is None else format(value.normalize(), "f")


def to_dict(row: AiModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "provider_name": PROVIDERS.get(row.provider, row.provider),
        "endpoint": row.endpoint,
        "web_search": row.web_search,
        "thinking": row.thinking,
        "reasoning_effort": row.reasoning_effort,
        "service_tier": row.service_tier,
        **{name: _price_text(getattr(row, name)) for name in _PRICE_FIELDS},
        "peak_hours": row.peak_hours,
        "rate_limit": row.rate_limit,
        "enabled": row.enabled,
        "sort_order": row.sort_order,
        "version": row.version,
        "created_at": format_beijing(row.created_at),
        "created_by_name": row.created_by_name,
        "updated_at": format_beijing(row.updated_at),
        "updated_by_name": row.updated_by_name,
    }


async def list_models(session: AsyncSession) -> list[dict[str, Any]]:
    return [to_dict(row) for row in await repo.list_all(session)]


async def enabled_models(session: AsyncSession) -> list[LlmModel]:
    return [to_model(row) for row in await repo.list_all(session, enabled_only=True)]


async def find(session: AsyncSession, model_id: str) -> AiModel | None:
    return await repo.get(session, model_id) if model_id else None


async def names(session: AsyncSession) -> dict[str, str]:
    return {row.id: row.name for row in await repo.list_all(session)}


def _price(values: dict[str, Any], key: str, label: str, *, required: bool) -> Decimal | None:
    text = str(values.get(key) if values.get(key) is not None else "").strip()
    if not text:
        if required:
            raise _invalid(f"请填写{label}")
        return None
    try:
        price = Decimal(text)
    except InvalidOperation:
        raise _invalid(f"{label}要填数字") from None
    if not price.is_finite() or price < 0 or price >= _PRICE_MAX:
        raise _invalid(f"{label}要在 0 到 1000 之间")
    exponent = price.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > _PRICE_PLACES:
        raise _invalid(f"{label}最多 6 位小数")
    return price


def _choice(values: dict[str, Any], key: str, allowed: tuple[str, ...], label: str) -> str:
    value = str(values.get(key) or "").strip()
    if value and value not in allowed:
        raise _invalid(f"{label}只能是 {'、'.join(allowed)} 或不填")
    return value


def _validated_prices(values: dict[str, Any], service_tier: str) -> dict[str, Any]:
    """单价成对校验：低优、高峰两档各自要么都填要么都不填；选了低优档就得有低优价。"""

    out: dict[str, Any] = {}
    out["input_price"] = _price(values, "input_price", "常规输入单价", required=True)
    out["output_price"] = _price(values, "output_price", "常规输出单价", required=True)
    out["search_price"] = _price(values, "search_price", "联网单价", required=False) or Decimal(0)
    out["flex_input_price"] = _price(values, "flex_input_price", "低优输入单价", required=False)
    out["flex_output_price"] = _price(values, "flex_output_price", "低优输出单价", required=False)
    if (out["flex_input_price"] is None) != (out["flex_output_price"] is None):
        raise _invalid("低优输入、输出单价要一起填或都不填")
    if service_tier == "flex" and out["flex_input_price"] is None:
        raise _invalid("服务档位选了低优，要填低优单价")
    out["peak_input_price"] = _price(values, "peak_input_price", "高峰输入单价", required=False)
    out["peak_output_price"] = _price(values, "peak_output_price", "高峰输出单价", required=False)
    if (out["peak_input_price"] is None) != (out["peak_output_price"] is None):
        raise _invalid("高峰输入、输出单价要一起填或都不填")
    peak_hours = str(values.get("peak_hours") or "").strip()
    if out["peak_input_price"] is not None:
        peak_hours = peak_hours or DEFAULT_PEAK_HOURS
        try:
            parse_peak_hours(peak_hours)
        except ValueError as exc:
            raise _invalid(f"高峰时段格式不对（{exc}），应形如 09:00-12:00,14:00-18:00") from None
    out["peak_hours"] = peak_hours if out["peak_input_price"] is not None else ""
    return out


def _validated(values: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, limit in _TEXT_LIMITS.items():
        out[key] = str(values.get(key) or "").strip()
        if len(out[key]) > limit:
            raise _invalid(f"内容过长（上限 {limit} 字）")
    if not out["name"]:
        raise _invalid("请填写显示名称")
    if not out["endpoint"]:
        raise _invalid("请填写接入点")
    provider = str(values.get("provider") or "").strip()
    if provider not in PROVIDERS:
        raise _invalid("请选择厂商")
    out["provider"] = provider
    out["thinking"] = _choice(values, "thinking", THINKING_MODES, "深度思考")
    out["reasoning_effort"] = _choice(values, "reasoning_effort", REASONING_EFFORTS, "思考强度")
    out["service_tier"] = _choice(values, "service_tier", SERVICE_TIERS, "服务档位")
    out["web_search"] = bool(values.get("web_search"))
    out["enabled"] = bool(values.get("enabled", True))
    out["sort_order"] = int(values.get("sort_order") or 0)
    out.update(_validated_prices(values, out["service_tier"]))
    return out


def _check_id(model_id: str) -> str:
    value = model_id.strip()
    if not _ID.fullmatch(value):
        raise _invalid("模型ID只能用中英文、数字、点、横线和下划线，最多 64 字")
    return value


async def create_model(session: AsyncSession, actor: Actor, values: dict[str, Any]) -> dict[str, Any]:
    model_id = _check_id(str(values.get("id") or ""))
    fields = _validated(values)
    if await repo.get(session, model_id) is not None:
        raise ApiError(f"模型ID「{model_id}」已存在", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    now = utcnow()
    row = AiModel(
        id=model_id,
        **fields,
        version=1,
        created_at=now,
        created_by_name=actor.name,
        updated_at=now,
        updated_by_name=actor.name,
    )
    repo.add(session, row)
    await session.flush()
    changes = {key: _audit_value(value) for key, value in fields.items()}
    await enqueue_event(session, event_type="ai.model.created", actor=actor, target_id=model_id, changes=changes)
    return to_dict(row)


def _audit_value(value: Any) -> Any:
    """审计内容存 JSONB，价格转成文本。"""

    return _price_text(value) if isinstance(value, Decimal) or value is None else value


def _changed(old: Any, new: Any) -> bool:
    return bool(_audit_value(old) != _audit_value(new))


async def update_model(session: AsyncSession, actor: Actor, model_id: str, values: dict[str, Any]) -> dict[str, Any]:
    row = await repo.get(session, model_id, lock=True)
    if row is None:
        raise NotFoundError("模型不存在")
    if values.get("version") != row.version:
        raise VersionConflictError()
    fields = _validated(values)
    changes = {
        key: {"from": _audit_value(getattr(row, key)), "to": _audit_value(value)}
        for key, value in fields.items()
        if _changed(getattr(row, key), value)
    }
    if not changes:
        return to_dict(row)
    for key in changes:
        setattr(row, key, fields[key])
    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_name = actor.name
    await enqueue_event(session, event_type="ai.model.updated", actor=actor, target_id=model_id, changes=changes)
    return to_dict(row)
