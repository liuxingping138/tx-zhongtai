"""从数据库取模板的测试数据：和正式打标交给模板的数据一模一样（同样的列名、同样整理过的正文）。

业务人员在提问配置里点「从数据库取测试数据」，取来的行存成模板的测试 Excel，之后试发、先跑几条都用它，
测出来的效果就是正式跑的效果。也可以照旧自己上传 Excel，造特殊用例。

- 类型判断：某个采集日的源政策，和类型判断按天读的一样。
- 政策解读：最近被判为「需要解读」的政策。
- 市场机会：最近解读过的政策，多一列 @【行业场景】（解读出的一级行业/一级场景）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import anyio
from platform_common.errors import ApiError, DependencyUnavailableError, ErrorCode, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.domain import interpret_rules, rules
from app.aitag.domain.contract import COLUMNS, REQUIRED_FIELDS
from app.aitag.domain.tasks import TASKS
from app.aitag.repositories import source
from app.aitag.repositories import tagging as repo

LIMIT_RANGE = (1, 50)


def contract() -> dict[str, Any]:
    """三个任务各给模板哪些列、要模板输出哪些字段。"""

    return {
        "tasks": [
            {"code": code, "name": name, "columns": list(COLUMNS[code]), "required_fields": list(REQUIRED_FIELDS[code])}
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


async def _source_rows(day: date, limit: int, max_chars: int) -> list[dict[str, str]]:
    rows = await _read(source.read_batch, day, "", limit, day)
    if not rows:
        raise _empty(f"{day.isoformat()} 这天源库没有采集到政策，换一天试试")
    contents = await _read(source.read_contents, [str(row["content_id"]) for row in rows])
    return [rules.prompt_row(row, contents.get(str(row["content_id"])), max_chars) for row in rows]


async def _tag_rows(session: AsyncSession, task: str, limit: int, max_chars: int) -> list[dict[str, str]]:
    tags = await repo.recent_tags(session, interpreted=task == "opportunity", limit=limit)
    if not tags:
        if task == "interpret":
            raise _empty("还没有被判为「需要解读」的政策：先跑一批政策类型判断，或改用类型判断的源政策测试")
        raise _empty("还没有解读过的政策：先跑一批政策解读")
    ids = [str(tag.source_content_id) for tag in tags]
    contents = await _read(source.read_contents, ids)
    rows = [
        interpret_rules.base_prompt_row(tag, rules.clean_content(contents.get(str(tag.source_content_id)), max_chars))
        for tag in tags
    ]
    if task == "interpret":
        return rows
    grouped = await repo.ai_interpretations(session, ids)
    return [
        interpret_rules.opportunity_prompt_row(
            row,
            [
                {"industry_l1": item.industry_l1, "scenario_l1_name": item.scenario_l1_name}
                for item in grouped.get(str(tag.source_content_id), [])
            ],
        )
        for tag, row in zip(tags, rows, strict=True)
    ]


async def samples(session: AsyncSession, task: str, day: date | None, limit: int) -> dict[str, Any]:
    if task not in TASKS:
        raise ApiError("不认识的打标任务", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not LIMIT_RANGE[0] <= limit <= LIMIT_RANGE[1]:
        raise ApiError(
            f"条数要在 {LIMIT_RANGE[0]}～{LIMIT_RANGE[1]} 之间", code=ErrorCode.VALIDATION_ERROR, http_status=422
        )
    # 正文长度按这个任务的设置截，和正式跑一致。
    max_chars = (await repo.task(session, task)).content_max_chars
    if task == "type":
        if day is None:
            raise ApiError("请选择采集日期", code=ErrorCode.VALIDATION_ERROR, http_status=422)
        rows = await _source_rows(day, limit, max_chars)
        origin = f"{day.isoformat()} 采集的源政策"
    else:
        rows = await _tag_rows(session, task, limit, max_chars)
        origin = "最近需要解读的政策" if task == "interpret" else "最近解读过的政策"
    headers = list(COLUMNS[task])
    return {
        "task": task,
        "file_name": f"数据库样本-{TASKS[task]}-{len(rows)}条.xlsx",
        "note": f"{origin} {len(rows)} 条，列和正文整理方式与「{TASKS[task]}」正式打标一致",
        "headers": headers,
        "rows": [[row.get(header, "") for header in headers] for row in rows],
    }
