"""信源 Excel 导入：逐行暂存 → 校验（文件内和库里重复、网站编码、省市区编码）→ 分配网站编码建行。

和新建、编辑共用一套校验和归一（sources 里的 _normalized_values、_overlong 等）。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.excel import parse_sheet_async
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.policy.application.importing import (
    add_in_batches,
    inserted_result,
    mark,
    missing_area_reason,
    rejected_result,
)
from app.policy.application.region import (
    SiteCodeAllocator,
    digits_only,
    make_internal_id,
    region_conflict,
    site_code_prefix,
)
from app.policy.application.source_status import beijing_today, online_date_after
from app.policy.application.sources import (
    NON_NUMERIC_AREA_CODE,
    ONLINE_DATE_ERROR,
    SITE_CODE_MAX_LENGTH,
    _has_any_area_code,
    _normalized_values,
    _overlong,
    normalize_online_date,
    site_code_prefix_of,
)
from app.policy.domain.fields import SOURCE_COLUMNS, crawler_status_error
from app.policy.domain.models import SOURCE_FIELDS, Source
from app.policy.repositories import sources as repo


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
        if not row.site_code and not site_code_prefix_of(row.values):
            filled = _has_any_area_code(row.values)
            reasons.append(NON_NUMERIC_AREA_CODE if filled else missing_area_reason(row.carried_reason))
        if message := region_conflict(
            row.values["province_code"], row.values["city_code"], row.values["district_code"]
        ):
            reasons.append(message)
        if not row.values["site_name"]:
            reasons.append("网站名称为空")
        if normalize_online_date(row.values["online_date"]) is None:
            reasons.append(ONLINE_DATE_ERROR)
        if message := crawler_status_error(row.values["crawler_status"]):
            reasons.append(message)
        reasons.extend(_overlong(row.values))
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
    allocator = SiteCodeAllocator(db_site | {row.site_code for row in staged if row.site_code})
    built: list[Source] = []
    for row in staged:
        normalized = _normalized_values(row.values)
        # 和新建一样：爬虫状态是「已爬」、上线时间没填的记为导入当天；文件里填了日期的照文件。
        normalized["online_date"] = online_date_after(
            "", normalized["crawler_status"], "", normalized["online_date"], today
        )
        site_code = row.site_code or allocator.allocate(
            site_code_prefix(normalized["province_code"], normalized["city_code"], normalized["district_code"])
        )
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
