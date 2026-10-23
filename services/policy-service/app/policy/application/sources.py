from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError, VersionConflictError
from platform_common.excel import build_workbook_async, parse_sheet_async
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.core.config import get_settings
from app.policy.application.importing import (
    add_in_batches,
    inserted_result,
    mark,
    missing_area_reason,
    rejected_result,
)
from app.policy.application.region import (
    digits_only,
    make_internal_id,
    next_site_code,
    normalize_region,
    site_code_prefix,
)
from app.policy.application.source_status import beijing_today, online_date_after
from app.policy.domain.fields import SOURCE_COLUMNS
from app.policy.domain.models import SOURCE_FIELDS, Source
from app.policy.repositories import options as options_repo
from app.policy.repositories import sources as repo

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


def _require_valid(values: dict[str, str]) -> None:
    if not values["site_name"]:
        raise ApiError("网站名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not _has_any_area_code(values):
        raise ApiError("省市区编码不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if normalize_online_date(values["online_date"]) is None:
        raise ApiError(ONLINE_DATE_ERROR, code=ErrorCode.VALIDATION_ERROR, http_status=422)


def _has_any_area_code(item: dict[str, str]) -> bool:
    return bool(
        (item.get("province_code") or "").strip()
        or (item.get("city_code") or "").strip()
        or (item.get("district_code") or "").strip()
    )


async def _allocate_site_code(session: AsyncSession, province_code: str, city_code: str, district_code: str) -> str:
    prefix = site_code_prefix(province_code, city_code, district_code)
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
    _require_valid(raw)
    values = _normalized_values(raw)
    values["online_date"] = online_date_after("", values["crawler_status"], "", values["online_date"], beijing_today())
    internal_id = make_internal_id(values["site_name"], values["province_name"], values["city_name"], values["tag"])
    if await repo.get_by_internal_id(session, internal_id):
        raise ApiError("已存在相同的内部唯一 id", code=ErrorCode.VERSION_CONFLICT, http_status=409)
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


async def update_source(
    session: AsyncSession, actor: Actor, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    row = await repo.get_for_update(session, item_id)
    if row is None:
        raise NotFoundError("信源不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()
    raw = {field: str(data.get(field, getattr(row, field) or "")).strip() for field in SOURCE_FIELDS}
    _require_valid(raw)
    values = _normalized_values(raw)
    values["online_date"] = online_date_after(
        row.crawler_status, values["crawler_status"], row.online_date, values["online_date"], beijing_today()
    )
    internal_id = make_internal_id(values["site_name"], values["province_name"], values["city_name"], values["tag"])
    existing = await repo.get_by_internal_id(session, internal_id)
    if existing and existing.id != row.id:
        raise ApiError("已存在相同的内部唯一 id", code=ErrorCode.VERSION_CONFLICT, http_status=409)
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


@dataclass(frozen=True, slots=True)
class _StagedSource:
    values: dict[str, str]
    internal_id: str
    site_code: str
    # 文件自带的校验说明，见 missing_area_reason。
    carried_reason: str


def _stage(item: dict[str, str]) -> _StagedSource:
    values = {field: (item.get(field) or "").strip() for field in SOURCE_FIELDS}
    return _StagedSource(
        values=values,
        internal_id=make_internal_id(values["site_name"], values["province_name"], values["city_name"], values["tag"]),
        site_code=(item.get("site_code") or "").strip(),
        carried_reason=(item.get("skip_reason") or "").strip(),
    )


def _site_code_reasons(site_code: str, db_site: set[str], file_site: Counter[str]) -> list[str]:
    if not site_code:
        return []
    reasons: list[str] = []
    if digits_only(site_code) != site_code or len(site_code) > SITE_CODE_MAX_LENGTH:
        reasons.append("网站编码不合法")
    elif site_code in db_site:
        reasons.append("网站编码已存在")
    if file_site[site_code] > 1:
        reasons.append("文件内网站编码重复")
    return reasons


def _check_rows(staged: list[_StagedSource], db_internal: set[str], db_site: set[str]) -> list[list[str]]:
    file_internal = Counter(row.internal_id for row in staged)
    file_site = Counter(row.site_code for row in staged if row.site_code)
    checked: list[list[str]] = []
    for row in staged:
        reasons: list[str] = []
        # 省市区编码只用来分配网站编码，自带网站编码的行可以不填。
        if not row.site_code and not _has_any_area_code(row.values):
            reasons.append(missing_area_reason(row.carried_reason))
        if not row.values["site_name"]:
            reasons.append("网站名称为空")
        if normalize_online_date(row.values["online_date"]) is None:
            reasons.append(ONLINE_DATE_ERROR)
        if row.internal_id in db_internal:
            reasons.append("内部唯一id已存在")
        if file_internal[row.internal_id] > 1:
            reasons.append("网站名称+省份+地市+标签重复")
        reasons.extend(_site_code_reasons(row.site_code, db_site, file_site))
        checked.append(reasons)
    return checked


def _build_rows(actor: Actor, staged: list[_StagedSource], db_site: set[str]) -> list[Source]:
    now = utcnow()
    today = beijing_today()
    taken = db_site | {row.site_code for row in staged if row.site_code}
    built: list[Source] = []
    for row in staged:
        normalized = _normalized_values(row.values)
        # 和新建一样：爬虫状态是「已爬」、上线时间没填的记为导入当天；文件里填了日期的照文件。
        normalized["online_date"] = online_date_after(
            "", normalized["crawler_status"], "", normalized["online_date"], today
        )
        site_code = row.site_code or next_site_code(
            site_code_prefix(normalized["province_code"], normalized["city_code"], normalized["district_code"]), taken
        )
        taken.add(site_code)
        built.append(
            Source(
                internal_id=row.internal_id,
                site_code=site_code,
                version=1,
                created_at=now,
                created_by_id=actor.id,
                created_by_name=actor.name,
                updated_at=now,
                updated_by_id=actor.id,
                updated_by_name=actor.name,
                **normalized,
            )
        )
    return built


async def import_sources(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, Any]:
    parsed = await parse_sheet_async(content, SOURCE_COLUMNS, subject="政策")
    staged = [_stage(item) for item in parsed]
    db_site = await repo.list_site_codes(session)
    checked = _check_rows(staged, await repo.list_internal_ids(session), db_site)
    blocked = sum(1 for reasons in checked if reasons)
    if blocked:
        marked = [
            mark({**row.values, "site_code": row.site_code}, reasons)
            for row, reasons in zip(staged, checked, strict=True)
        ]
        return await rejected_result(SOURCE_COLUMNS, marked, blocked=blocked)
    inserted = await add_in_batches(session, _build_rows(actor, staged, db_site))
    await enqueue_event(
        session,
        event_type="policy.source.imported",
        actor=actor,
        extra={"inserted": inserted, "skipped": 0},
    )
    return inserted_result(inserted)


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
    return await build_workbook_async(SOURCE_COLUMNS, rows, sheet_name="网站编码")
