from __future__ import annotations

import logging
import uuid
from collections import Counter
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.columns import overlong_reasons, string_lengths
from platform_common.errors import ApiError, DependencyUnavailableError, ErrorCode, NotFoundError, VersionConflictError
from platform_common.excel import build_workbook_async, parse_sheet_async
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import internal_clients
from app.common.audit_emit import enqueue_event
from app.core.config import get_settings
from app.policy.application.importing import (
    add_in_batches,
    inserted_result,
    mark,
    missing_area_reason,
    rejected_result,
)
from app.policy.application.policy_content import policy_content
from app.policy.domain.fields import BASE_TAG_COLUMNS, ai_status
from app.policy.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash
from app.policy.repositories import base_tags as repo
from app.policy.repositories import options as options_repo

BASE_TAG_LENGTHS = string_lengths(BaseTag)

logger = logging.getLogger("policy.base_tags")


def _to_out(row: BaseTag) -> dict[str, Any]:
    data: dict[str, Any] = row.business_values()
    data["id"] = str(row.id)
    data["version"] = row.version
    data["created_at"] = format_beijing(row.created_at)
    data["created_by_name"] = row.created_by_name
    data["updated_at"] = format_beijing(row.updated_at)
    data["updated_by_name"] = row.updated_by_name
    # 只给列表看，不进 Excel：导出、导入的列仍是 BASE_TAG_COLUMNS。
    data["ai_status"] = ai_status(
        remark=row.remark,
        source_content_id=row.source_content_id,
        need_interpret=row.need_interpret,
        type_retag_at=row.type_retag_at,
        interpreted_at=row.interpreted_at,
        opportunity_at=row.opportunity_at,
    )
    return data


def _values(data: dict[str, str]) -> dict[str, str]:
    return {field: (data.get(field) or "").strip() for field in BASE_TAG_FIELDS}


async def list_base_tags(
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


async def list_base_tag_options(session: AsyncSession) -> dict[str, Any]:
    data = await options_repo.base_tag_options(session)
    # 政策类型的候选值是政策类型码表，不在几百万条政策上去重。码表服务暂时取不到时下拉为空，仍可输入后回车。
    try:
        names = await internal_clients.policy_type_names()
    except DependencyUnavailableError:
        logger.warning("政策类型码表暂时取不到，筛选项先不给政策类型")
        names = []
    data["options"]["policy_types"] = {"items": names, "truncated": False}
    return data


async def search_base_tag_options(session: AsyncSession, *, field: str, keyword: str | None) -> list[str]:
    """按关键词搜索筛选项候选值，供前端下拉的服务端搜索使用。"""

    return await options_repo.search(session, options_repo.BASE_TAG_OPTION_COLUMNS, field=field, keyword=keyword)


async def get_base_tag(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("政策基础标签不存在")
    return _to_out(row)


async def base_tag_content(session: AsyncSession, item_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.get_by_id(session, item_id)
    if row is None:
        raise NotFoundError("政策基础标签不存在")
    return await policy_content(row.source_content_id)


def _require_lengths(values: dict[str, str]) -> None:
    if reasons := overlong_reasons(values, BASE_TAG_COLUMNS, BASE_TAG_LENGTHS):
        raise ApiError("、".join(reasons), code=ErrorCode.VALIDATION_ERROR, http_status=422)


async def update_base_tag(
    session: AsyncSession, actor: Actor, item_id: uuid.UUID, data: dict[str, Any]
) -> dict[str, Any]:
    row = await repo.get_for_update(session, item_id)
    if row is None:
        raise NotFoundError("政策基础标签不存在")
    if data.get("version") != row.version:
        raise VersionConflictError()
    values = _values({field: str(data.get(field, getattr(row, field) or "")) for field in BASE_TAG_FIELDS})
    if not values["policy_name"]:
        raise ApiError("政策名称不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    _require_lengths(values)
    digest = content_hash(values, BASE_TAG_FIELDS)
    existing = await repo.get_by_hash(session, digest)
    if existing and existing.id != row.id:
        raise ApiError("已有一条内容完全相同的政策基础标签，不能重复", code=ErrorCode.DUPLICATE, http_status=409)
    changes: dict[str, Any] = {}
    for field, new in values.items():
        old = getattr(row, field) or ""
        if old != new:
            changes[field] = {"from": old[:80], "to": new[:80]}
            setattr(row, field, new)
    if not changes:
        return _to_out(row)
    row.refresh_hash()
    row.version += 1
    row.updated_at = utcnow()
    row.updated_by_id = actor.id
    row.updated_by_name = actor.name
    await enqueue_event(
        session,
        event_type="policy.base_tag.updated",
        actor=actor,
        target_id=str(row.id),
        changes=changes,
    )
    return _to_out(row)


def _has_any_area_code(item: dict[str, str]) -> bool:
    return bool((item.get("province_code") or "").strip() or (item.get("city_code") or "").strip())


def _check_rows(staged: list[tuple[dict[str, str], str, str]], db_hashes: set[str]) -> list[list[str]]:
    file_hashes = Counter(digest for _values, digest, _reason in staged)
    checked: list[list[str]] = []
    for values, digest, carried_reason in staged:
        reasons: list[str] = []
        if not _has_any_area_code(values):
            reasons.append(missing_area_reason(carried_reason))
        if not values["policy_name"]:
            reasons.append("政策名称为空")
        reasons.extend(overlong_reasons(values, BASE_TAG_COLUMNS, BASE_TAG_LENGTHS))
        if digest in db_hashes:
            reasons.append("内容已存在")
        if file_hashes[digest] > 1:
            reasons.append("文件内内容重复")
        checked.append(reasons)
    return checked


async def import_base_tags(session: AsyncSession, actor: Actor, content: bytes) -> dict[str, Any]:
    parsed = await parse_sheet_async(content, BASE_TAG_COLUMNS, subject="政策")
    staged: list[tuple[dict[str, str], str, str]] = []
    for item in parsed:
        values = _values(item)
        staged.append((values, content_hash(values, BASE_TAG_FIELDS), (item.get("skip_reason") or "").strip()))
    checked = _check_rows(staged, await repo.existing_hashes(session, [digest for _values, digest, _reason in staged]))
    blocked = sum(1 for reasons in checked if reasons)
    if blocked:
        marked = [mark(values, reasons) for (values, _digest, _reason), reasons in zip(staged, checked, strict=True)]
        return await rejected_result(BASE_TAG_COLUMNS, marked, blocked=blocked)
    now = utcnow()
    rows = (
        BaseTag(
            content_hash=digest,
            version=1,
            created_at=now,
            created_by_id=actor.id,
            created_by_name=actor.name,
            updated_at=now,
            updated_by_id=actor.id,
            updated_by_name=actor.name,
            **values,
        )
        for values, digest, _reason in staged
    )
    inserted = await add_in_batches(session, rows)
    await enqueue_event(
        session,
        event_type="policy.base_tag.imported",
        actor=actor,
        extra={"inserted": inserted, "skipped": 0},
    )
    return inserted_result(inserted)


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


async def export_base_tags(session: AsyncSession, actor: Actor, filters: Filters) -> bytes:
    await _assert_exportable(session, filters)
    rows = [_to_out(item) for item in await repo.list_filtered(session, filters)]
    await enqueue_event(
        session,
        event_type="policy.base_tag.exported",
        actor=actor,
        extra={"count": len(rows)},
    )
    return await build_workbook_async(BASE_TAG_COLUMNS, rows, sheet_name="政策基础标签表")
