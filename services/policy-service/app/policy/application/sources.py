from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.columns import overlong_reasons, string_lengths
from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from platform_common.excel import build_workbook_async
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.core.config import get_settings
from app.policy.application.region import (
    make_internal_id,
    next_site_code,
    normalize_region,
    region_conflict,
    site_code_prefix,
)
from app.policy.application.source_status import beijing_today, online_date_after
from app.policy.domain.fields import SOURCE_COLUMNS, crawler_status_error
from app.policy.domain.models import SOURCE_FIELDS, Source
from app.policy.repositories import options as options_repo
from app.policy.repositories import sources as repo

SOURCE_LENGTHS = string_lengths(Source)

# 与 policy_sources.site_code 的 String(16) 一致。
SITE_CODE_MAX_LENGTH = 16
ONLINE_DATE_ERROR = "上线时间格式不对，应为 YYYY-MM-DD"
# Excel 日期单元格读出来是「2024-01-02 00:00:00」，手填常见「2024/1/2」「2024年1月2日」。
_ONLINE_DATE = re.compile(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:[ T]00:00(?::00)?)?")


def normalize_online_date(text: str) -> str | None:
    """上线时间统一成 YYYY-MM-DD；空值原样返回空串，认不出的日期返回 None。"""

    if not text:
        return ""
    match = _ONLINE_DATE.fullmatch(text)
    if match is None:
        return None
    try:
        return date(*(int(part) for part in match.groups())).isoformat()
    except ValueError:  # 2024-02-30 这类不存在的日期
        return None


def _to_out(row: Source) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "internal_id": row.internal_id,
        "site_code": row.site_code,
        "province_name": row.province_name,
        "province_code": row.province_code,
        "city_name": row.city_name,
        "city_code": row.city_code,
        "district_name": row.district_name,
        "district_code": row.district_code,
        "site_name": row.site_name,
        "site_type": row.site_type,
        "crawler_status": row.crawler_status,
        "online_date": row.online_date,
        "crawl_priority": row.crawl_priority,
        "url": row.url,
        "tag": row.tag,
        "data_type": row.data_type,
        "department": row.department,
        "version": row.version,
        "created_at": format_beijing(row.created_at),
        "created_by_name": row.created_by_name,
        "updated_at": format_beijing(row.updated_at),
        "updated_by_name": row.updated_by_name,
    }


def _normalized_values(data: dict[str, str]) -> dict[str, str]:
    values = {field: (data.get(field) or "").strip() for field in SOURCE_FIELDS}
    province_code, city_code, district_code = normalize_region(
        values["province_code"], values["city_code"], values["district_code"]
    )
    values["province_code"] = province_code
    values["city_code"] = city_code
    values["district_code"] = district_code
    # 不合法的日期已在前面拦下（_require_valid / _check_rows），这里只做格式统一。
    values["online_date"] = normalize_online_date(values["online_date"]) or values["online_date"]
    return values


def _require_valid(values: dict[str, str], *, allocate_site_code: bool) -> None:
    """allocate_site_code：要不要按省市区编码分配网站编码（新建要，编辑不要）。省市区编码只用来分配网站编码，
    带着网站编码导入的全国、国央企信源本来就没有区划编码，编辑时也要求的话这类信源就改不了了。"""

    if not values["site_name"]:
        raise ApiError("网站名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if allocate_site_code and not site_code_prefix_of(values):
        raise ApiError(NON_NUMERIC_AREA_CODE, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if message := region_conflict(values["province_code"], values["city_code"], values["district_code"]):
        raise ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if normalize_online_date(values["online_date"]) is None:
        raise ApiError(ONLINE_DATE_ERROR, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if message := crawler_status_error(values["crawler_status"]):
        raise ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if reasons := _overlong(values):
        raise ApiError("、".join(reasons), code=ErrorCode.VALIDATION_ERROR, http_status=422)


def _overlong(values: dict[str, str]) -> list[str]:
    # 上线时间按入库的格式量（Excel 日期读出来带 00:00:00，归一后才是 10 位）。
    normalized = {**values, "online_date": normalize_online_date(values["online_date"]) or values["online_date"]}
    return overlong_reasons(normalized, SOURCE_COLUMNS, SOURCE_LENGTHS)


# 填了「北京」、或者只有 1 位数字时，网站编码前缀是空的：原来会分到 000000 前缀下，取号时还按空前缀
# LIKE '%' FOR UPDATE 锁住整张信源表。
NON_NUMERIC_AREA_CODE = "省市区编码要填数字编码（省至少 2 位，如 11、1101、110101），分配网站编码要用"


def site_code_prefix_of(item: dict[str, str]) -> str:
    """按这行的省市区编码分配网站编码用的 6 位前缀；编码不够用时为空。"""

    return site_code_prefix(
        item.get("province_code") or "", item.get("city_code") or "", item.get("district_code") or ""
    )


def _has_any_area_code(item: dict[str, str]) -> bool:
    return bool(
        (item.get("province_code") or "").strip()
        or (item.get("city_code") or "").strip()
        or (item.get("district_code") or "").strip()
    )


async def _allocate_site_code(session: AsyncSession, province_code: str, city_code: str, district_code: str) -> str:
    prefix = site_code_prefix(province_code, city_code, district_code)
    if not prefix:
        raise ApiError(NON_NUMERIC_AREA_CODE, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    existing = await repo.list_site_codes_for_district(session, prefix)
    return next_site_code(prefix, existing)


async def list_sources(
    session: AsyncSession,
    filters: Filters,
    *,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    items, total = await repo.list_items(
        session,
        filters=filters,
        page=page,
        page_size=page_size,
    )
    return {"items": [_to_out(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def list_source_options(session: AsyncSession) -> dict[str, Any]:
    return await options_repo.source_options(session)


async def search_source_options(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    """按关键词搜索筛选项候选值，供前端下拉的服务端搜索使用。"""

    return await options_repo.search(session, options_repo.SOURCE_OPTION_COLUMNS, field=field, keyword=keyword)


async def get_source(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("信源不存在")
    return _to_out(row)


async def create_source(session: AsyncSession, actor: Actor, data: dict[str, str]) -> dict[str, Any]:
    raw = {field: (data.get(field) or "").strip() for field in SOURCE_FIELDS}
    _require_valid(raw, allocate_site_code=True)
    values = _normalized_values(raw)
    values["online_date"] = online_date_after("", values["crawler_status"], "", values["online_date"], beijing_today())
    internal_id = make_internal_id(values["site_name"], values["province_name"], values["city_name"], values["tag"])
    if await repo.get_by_internal_id(session, internal_id):
        raise ApiError(
            "已有网站名称、省份、地市、标签都相同的信源（内部唯一 id 重复）", code=ErrorCode.DUPLICATE, http_status=409
        )
    site_code = await _allocate_site_code(
        session, values["province_code"], values["city_code"], values["district_code"]
    )
    if await repo.get_by_site_code(session, site_code):
        raise ApiError("网站编码冲突，请重试", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    now = utcnow()
    row = Source(
        internal_id=internal_id,
        site_code=site_code,
        version=1,
        created_at=now,
        created_by_id=actor.id,
        created_by_name=actor.name,
        updated_at=now,
        updated_by_id=actor.id,
        updated_by_name=actor.name,
        **values,
    )
    session.add(row)
    await session.flush()
    await enqueue_event(
        session,
        event_type="policy.source.created",
        actor=actor,
        target_id=str(row.id),
        changes={"site_code": site_code, "site_name": row.site_name},
    )
    return _to_out(row)


def _value(data: dict[str, Any], field: str, row: Source) -> Any:
    """表单里没给的字段沿用原值；给了 null（清空日期框）就是空。原来 str(None) 会存成「None」。"""

    return data[field] if field in data else getattr(row, field)


async def update_source(
    session: AsyncSession, actor: Actor, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    row = await repo.get_for_update(session, item_id)
    if row is None:
        raise NotFoundError("信源不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()
    raw = {field: str(_value(data, field, row) or "").strip() for field in SOURCE_FIELDS}
    _require_valid(raw, allocate_site_code=False)
    values = _normalized_values(raw)
    values["online_date"] = online_date_after(
        row.crawler_status, values["crawler_status"], row.online_date, values["online_date"], beijing_today()
    )
    internal_id = make_internal_id(values["site_name"], values["province_name"], values["city_name"], values["tag"])
    existing = await repo.get_by_internal_id(session, internal_id)
    if existing and existing.id != row.id:
        raise ApiError(
            "已有网站名称、省份、地市、标签都相同的信源（内部唯一 id 重复）", code=ErrorCode.DUPLICATE, http_status=409
        )
    changes: dict[str, Any] = {}
    for field, new in values.items():
        old = getattr(row, field) or ""
        if old != new:
            changes[field] = {"from": old[:80], "to": new[:80]}
            setattr(row, field, new)
    if row.internal_id != internal_id:
        changes["internal_id"] = {"from": row.internal_id, "to": internal_id}
        row.internal_id = internal_id
    if not changes:
        return _to_out(row)
    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_id = actor.id
    row.updated_by_name = actor.name
    await enqueue_event(
        session,
        event_type="policy.source.updated",
        actor=actor,
        target_id=str(row.id),
        changes=changes,
    )
    return _to_out(row)


async def purge_sources(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    deleted = await repo.delete_all(session)
    await enqueue_event(
        session,
        event_type="policy.source.purged",
        actor=actor,
        extra={"deleted": deleted},
    )
    return {"deleted": deleted}


async def _assert_exportable(session: AsyncSession, filters: Filters) -> None:
    """导出前按当前筛选条件校验行数上限。

    导出是把结果集整个读进内存再生成 Excel，没有上限时大表会把服务撑爆。
    上限由 ``export_max_rows`` 配置，默认 10 万行；超限时提示先缩小筛选范围。
    """

    limit = get_settings().export_max_rows
    total = await repo.count_filtered(session, filters)
    if total > limit:
        scope = "筛选结果" if any(filters.values()) else "本表"
        raise ApiError(
            f"{scope}共 {total} 条，超过单次导出上限 {limit} 条，请先缩小筛选范围后再导出。",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )


async def export_sources(session: AsyncSession, actor: Actor, filters: Filters) -> bytes:
    await _assert_exportable(session, filters)
    rows = [_to_out(item) for item in await repo.list_filtered(session, filters)]
    await enqueue_event(
        session,
        event_type="policy.source.exported",
        actor=actor,
        extra={"count": len(rows)},
    )
    return await build_workbook_async(SOURCE_COLUMNS, rows, sheet_name="信源管理")
