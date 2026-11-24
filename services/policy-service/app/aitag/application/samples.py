"""从数据库取模板的测试数据：和正式打标交给模板的数据一模一样（同样的列名、同样整理过的正文）。

业务人员在提示词模板页点「从数据库取」，取来的行存成模板的测试样本，之后试发、样本试跑都用它，
测出来的效果就是正式跑的效果。也可以照旧自己上传 Excel，造特殊用例。

- 类型判断：某个采集日的源政策，和类型判断按天读的一样。
- 政策解读：最近被判为「需要解读」的政策。
- 市场机会：最近解读过的政策，按解读出的（一级行业、一级场景）一组一行，和定时任务一样只用没人改过的解读行。

页面在等，所以：不加行锁，查询最多跑 15 秒，返回的总字数有上限（前端还要原样发给 AI 服务，网关收 20MB）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import anyio
from platform_common.errors import ApiError, DependencyUnavailableError, ErrorCode, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.application import scenario_describing, scenario_similar
from app.aitag.application.interpreting import untouched
from app.aitag.domain import interpret_rules, rules
from app.aitag.domain.contract import COLUMNS, OPTIONAL_FIELDS, REQUIRED_FIELDS
from app.aitag.domain.tasks import TASKS
from app.aitag.repositories import source
from app.aitag.repositories import tagging as repo

LIMIT_RANGE = (1, 500)
# 一次返回的总字数上限。前端拿到后原样发给 AI 服务（UTF-8 一个汉字 3 字节），要远低于网关 20MB 的请求上限；
# AI 服务那边按同一个数拦（batch_start.ROWS_CHARS_MAX）。
CHARS_BUDGET = 5_000_000
# 市场机会先多取几条政策候选：有的政策没有能用的行业场景，按条数只取 limit 条会凑不够 limit 组。
OPPORTUNITY_CANDIDATES = (50, 500)


@dataclass(frozen=True)
class SampleFilter:
    """抽样可选筛选条件：省份、政策名称关键词、一级行业（市场机会用）。"""

    province: str = ""
    keyword: str = ""
    industry_l1: str = ""

    @property
    def active(self) -> bool:
        return bool(self.province.strip() or self.keyword.strip() or self.industry_l1.strip())


async def contract(session: AsyncSession) -> dict[str, Any]:
    """三个任务各给模板哪些列、要模板输出哪些字段，以及现在用的是哪个模板（模板页据此说清上线影响谁）。"""

    configured = await repo.tasks(session)
    return {
        "tasks": [
            {
                "code": code,
                "name": name,
                "columns": list(COLUMNS[code]),
                "required_fields": list(REQUIRED_FIELDS[code]),
                "optional_fields": [list(group) for group in OPTIONAL_FIELDS[code]],
                "prompt_id": task.prompt_id if (task := configured.get(code)) else "",
            }
            for code, name in TASKS.items()
        ]
    }


def _empty(message: str) -> ApiError:
    return NotFoundError(message)


SOURCE_DOWN = "源库暂时连不上，取不了测试数据。可以先上传 Excel 测试，或稍后再试"


async def _read(func: Any, *args: Any) -> Any:
    """读源库；连不上时说清楚怎么办，别让页面只看到「服务器内部错误」。"""

    try:
        return await anyio.to_thread.run_sync(func, *args)
    except Exception as exc:
        raise DependencyUnavailableError(SOURCE_DOWN) from exc


async def _source_rows(day: date, limit: int, max_chars: int, province: str | None = None) -> list[dict[str, str]]:
    picked = [province.strip()] if province and province.strip() else []
    rows, contents = await _read(source.read_day_for_page, day, limit, picked)
    if not rows:
        scope = f"（{picked[0]}）" if picked else ""
        raise _empty(f"{day.isoformat()} 这天源库没有采集到政策{scope}，换一天或放宽省份试试")
    return [rules.prompt_row(row, contents.get(str(row["content_id"])), max_chars) for row in rows]


def _sample_pairs(rows: list[Any], industry: str) -> list[dict[str, str]]:
    """这条政策拿来做市场机会样本的组：优先用没人改过的 AI 行（定时任务只问这些）；
    都被人核对过、改过的，退到它所有有名称的行，取测试数据不该因此拿不到。"""

    picked = [row for row in rows if untouched(row)] or rows
    return [
        {"industry_l1": row.industry_l1, "scenario_l1_name": row.scenario_l1_name}
        for row in picked
        if not industry or row.industry_l1.strip() == industry
    ]


def _no_tags(task: str, flt: SampleFilter) -> ApiError:
    if flt.active:
        return _empty("按当前筛选条件没有找到匹配的政策，请放宽条件重试")
    if task == "interpret":
        return _empty("还没有被判为「需要解读」的政策：请先在任务调度跑一批政策类型判断，或先上传 Excel 测试")
    return _empty("还没有解读过的政策：请先在任务调度跑一批政策类型判断和政策解读，或先上传 Excel 测试")


async def _base_rows(tags: list[Any], max_chars: int) -> list[dict[str, str]]:
    contents = await _read(source.read_contents_for_page, [str(tag.source_content_id) for tag in tags])
    return [
        interpret_rules.base_prompt_row(tag, rules.clean_content(contents.get(str(tag.source_content_id)), max_chars))
        for tag in tags
    ]


async def _tag_rows(
    session: AsyncSession, task: str, limit: int, max_chars: int, flt: SampleFilter
) -> list[dict[str, str]]:
    opportunity = task == "opportunity"
    wanted = min(max(limit * 2, OPPORTUNITY_CANDIDATES[0]), OPPORTUNITY_CANDIDATES[1]) if opportunity else limit
    tags = await repo.recent_tags(
        session,
        interpreted=opportunity,
        limit=wanted,
        province=flt.province,
        keyword=flt.keyword,
        industry_l1=flt.industry_l1 if opportunity else None,
    )
    if not tags:
        raise _no_tags(task, flt)
    if not opportunity:
        return await _base_rows(tags, max_chars)
    grouped = await repo.interpretations_by_source_ids(session, [str(tag.source_content_id) for tag in tags])
    industry = flt.industry_l1.strip()
    # 先按组数挑出要用的政策，再只读这几条的正文：候选多取了，不能把用不上的也去源库读一遍。
    plans: list[tuple[Any, list[dict[str, str]]]] = []
    count = 0
    for tag in tags:
        pairs = _sample_pairs(grouped.get(str(tag.source_content_id), []), industry)
        groups = len(interpret_rules.opportunity_prompt_rows({}, pairs))
        if groups:
            plans.append((tag, pairs))
            count += groups
        if count >= limit:
            break
    if not plans:
        raise _empty("这些已解读政策还没有匹配的行业场景记录，请先跑政策解读或调整一级行业筛选")
    bases = await _base_rows([tag for tag, _ in plans], max_chars)
    expanded = [
        prompt_row
        for base, (_, pairs) in zip(bases, plans, strict=True)
        for _, prompt_row in interpret_rules.opportunity_prompt_rows(base, pairs)
    ]
    return expanded[:limit]


def _within_budget(rows: list[list[str]]) -> list[list[str]]:
    """按总字数截断，至少留一行；截掉的在 note 里说明。"""

    used = 0
    for index, row in enumerate(rows):
        used += sum(len(cell) for cell in row)
        if used > CHARS_BUDGET and index:
            return rows[:index]
    return rows


async def samples(
    session: AsyncSession,
    task: str,
    day: date | None,
    limit: int,
    flt: SampleFilter | None = None,
) -> dict[str, Any]:
    if task not in TASKS:
        raise ApiError("不认识的打标任务", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not LIMIT_RANGE[0] <= limit <= LIMIT_RANGE[1]:
        raise ApiError(
            f"条数要在 {LIMIT_RANGE[0]}～{LIMIT_RANGE[1]} 之间", code=ErrorCode.VALIDATION_ERROR, http_status=422
        )
    criteria = flt or SampleFilter()
    await repo.limit_sample_queries(session)
    # 正文长度按这个任务的设置截，和正式跑一致。
    max_chars = (await repo.task(session, task)).content_max_chars
    if task == "enrich":
        items = await scenario_describing.backlog(limit)
        if not items:
            raise _empty("码表里没有待补描述的新增场景：先在新增场景审核里采纳几个")
        rows = scenario_describing.prompt_rows(items)
        origin = "待补描述的新增场景"
    elif task == "scenario":
        candidates = await repo.scenario_backlog(session, limit) or await repo.pending_candidates(session, limit)
        if not candidates:
            raise _empty("新增场景审核里还没有待审的场景：先跑一批政策解读")
        rows, _ = await scenario_similar.prompt_rows(session, candidates)
        origin = "待审的新增场景"
    elif task == "type":
        if day is None:
            raise ApiError("请选择采集日期", code=ErrorCode.VALIDATION_ERROR, http_status=422)
        rows = await _source_rows(day, limit, max_chars, province=criteria.province)
        origin = f"{day.isoformat()} 采集的源政策"
    else:
        rows = await _tag_rows(session, task, limit, max_chars, criteria)
        origin = "最近需要解读的政策" if task == "interpret" else "最近解读过的政策（按一级行业+一级场景展开）"
    headers = list(COLUMNS[task])
    values = _within_budget([[row.get(header, "") for header in headers] for row in rows])
    note = f"{origin} {len(values)} 条，列和正文整理方式与「{TASKS[task]}」正式打标一致"
    if len(values) < len(rows):
        note += f"；总字数超过 {CHARS_BUDGET // 10_000} 万字，只取了前 {len(values)} 条，可以改成截取正文或减少条数"
    return {
        "task": task,
        "file_name": f"数据库样本-{TASKS[task]}-{len(values)}条.xlsx",
        "note": note,
        "headers": headers,
        "rows": values,
    }
