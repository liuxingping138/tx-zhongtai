"""新增场景补描述：码表里待补充的新场景（采纳进来时只有名称）交给上线模板写描述，写回码表标「待确认」。

一个场景（按场景路径，各行业各客群的行一起）只问一次；AI 没写出来的也标待确认、描述空着让人补，免得每批都重问。
"""

from __future__ import annotations

import uuid
from typing import Any

from app.aitag.application.pipeline import Spend, ask, not_run, reused_note, update_run
from app.aitag.domain.describing import FIELD_COLUMNS, LEVEL_NAMES, NONE, PATH_COLUMN
from app.aitag.domain.models import PolicyAiTask
from app.common import internal_clients


async def backlog(limit: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = await internal_clients.codebook(
        "POST", "/internal/v1/scenarios/enrich-backlog", json={"limit": limit}
    )
    return found


def prompt_rows(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """交给模板的行（列见 domain.describing.COLUMNS）。"""

    rows = []
    for item in items:
        examples = "\n".join(f"{e.get('name')}：{e.get('desc')}" for e in item.get("examples") or [])
        rows.append(
            {
                PATH_COLUMN: str(item.get("key") or ""),
                "新增级别": LEVEL_NAMES.get(int(item.get("level") or 0), ""),
                "所属行业": "、".join(item.get("industries") or []),
                "来源政策": str(item.get("source_policy") or "") or NONE,
                "上级场景描述": str(item.get("parent_desc") or "") or NONE,
                "同级场景示例": examples or NONE,
            }
        )
    return rows


def answers(items: list[dict[str, Any]], results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    """模型的回答整理成写回码表的内容。没轮到的不写（下批再问）；失败的只改状态、描述空着。"""

    out: list[dict[str, Any]] = []
    done = failed = 0
    for item, result in zip(items, results, strict=True):
        if not_run(result):
            continue
        first = (result.get("items") or [{}])[0] if not result.get("error") else {}
        if not first:
            failed += 1
            out.append({"path": item["path"]})
            continue
        done += 1
        out.append(
            {"path": item["path"], **{column: str(first.get(field) or "") for field, column in FIELD_COLUMNS.items()}}
        )
    return out, done, failed


async def describe_step(run_id: uuid.UUID, config: PolicyAiTask, spend: Spend) -> str:
    items = await backlog(config.batch_size)
    if not items:
        return "没有待补描述的新增场景"
    await update_run(run_id, stage="describing", source_rows=len(items))
    status, results = await ask(
        run_id,
        spend,
        prompt_id=config.prompt_id,
        rows=prompt_rows(items),
        caller="政策AI打标·新增场景补描述",
        run_field="enrich_run_id",
    )
    written, done, failed = answers(items, results)
    if written:
        await internal_clients.codebook("POST", "/internal/v1/scenarios/enrich", json={"items": written})
    await update_run(run_id, enrich_rows=done, enrich_failed=failed)
    note = (
        f"{len(items)} 个新增场景{reused_note(status)}，AI 写好描述 {done} 个，没写出来 {failed} 个（描述空着，待人补）"
    )
    left = len(items) - len(written)
    if left:
        note += f"；{status.get('error_message') or '任务提前停止'}，{left} 个下批接着写"
    return note
