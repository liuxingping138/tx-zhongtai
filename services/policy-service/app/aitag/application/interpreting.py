"""打标的后两步，按待办做：

2. 政策解读：基础标签里「是否解读 = 是」、还没解读的政策 → 用上线模板解读 → 一条政策展开成多行写进政策解读表。
3. 市场机会：解读过、还没做市场机会的政策 → 用上线模板写市场机会 → 按一级行业 + 一级场景回填到它的解读行。

费用到上限没轮到的政策不记进度，下一批接着做。AI 写的行只要人工核对过（人工验证）或改过，就不再覆盖。
"""

from __future__ import annotations

import uuid
from typing import Any

import anyio
from platform_common.clock import utcnow

from app.aitag.application.pipeline import ROBOT, Spend, ask, not_run, reused_note, update_run
from app.aitag.domain import interpret_rules as rules
from app.aitag.domain.models import PolicyAiTask
from app.aitag.domain.rules import INTERPRET_FAILED, NOTE_SEP, OPPORTUNITY_FAILED, clean_content
from app.aitag.repositories import source
from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.common.audit_emit import enqueue_event
from app.core.database import SessionLocal
from app.policy.domain.fields import DATA_STATUS_PENDING
from app.policy.domain.models import BaseTag, Interpretation


def untouched(row: Interpretation) -> bool:
    """AI 写的、还没人核对或改过的行，可以被重新解读替换或回填。"""

    return (
        row.data_status == DATA_STATUS_PENDING
        and row.tagged_at is not None
        and row.updated_at <= row.tagged_at
        and row.source_content_id is not None
    )


def _append_remark(tag: BaseTag, message: str) -> None:
    """备注里写上失败原因。版本号要加：有人正开着这条在核对页编辑，保存时才会提示「被改过」，不会把这句说明冲掉。
    内容哈希不重算：同一网页采了几条时，加一句说明就可能和另一条一模一样，撞唯一约束、整批回滚。"""

    tag.remark = f"{tag.remark}{NOTE_SEP}{message}" if tag.remark else message
    tag.version += 1


async def _prompt_rows(tags: list[BaseTag], max_chars: int) -> list[dict[str, str]]:
    ids = [str(tag.source_content_id) for tag in tags]
    contents = await anyio.to_thread.run_sync(source.read_contents, ids)
    return [
        rules.base_prompt_row(tag, clean_content(contents.get(str(tag.source_content_id)), max_chars)) for tag in tags
    ]


async def _codes(results: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """模型说「不是新增」的场景去码表查编码：六级名称对上，或按一级行业对上通用场景。"""

    items = []
    for index, result in enumerate(results):
        for position, item in enumerate(result.get("items") or []):
            values = rules.interpretation_values(item)
            if values["is_new_scenario"] == "否":
                names = dict(zip(rules.LEVEL_FIELDS, rules.scenario_names(values), strict=True))
                items.append({"key": f"{index}:{position}", **names})
    if not items:
        return {}
    found = await internal_clients.codebook("POST", "/internal/v1/scenarios/lookup", json={"items": items})
    return {str(item["key"]): item for item in found if item.get("industry_scenario_code")}


def _new_row(tag: BaseTag, values: dict[str, str], key: str) -> Interpretation:
    now = utcnow()
    return Interpretation(
        record_id=str(uuid.uuid4()),
        tenant_id="",
        policy_uid=str(tag.source_content_id)[: rules.UID_MAX],
        policy_title=tag.policy_name,
        relation_key=key,
        source_content_id=str(tag.source_content_id),
        tagged_at=now,
        data_status=DATA_STATUS_PENDING,
        market_opportunity="",
        version=1,
        created_at=now,
        created_by_id=ROBOT.id,
        created_by_name=ROBOT.name,
        updated_at=now,
        updated_by_id=ROBOT.id,
        updated_by_name=ROBOT.name,
        **values,
    )


def _row_values(item: dict[str, Any], codes: dict[str, str] | None) -> dict[str, str]:
    values = rules.interpretation_values(item)
    values.update(industry_scenario_code="", industry_code="", scenario_code="")
    if codes:
        for field in ("industry_scenario_code", "industry_code", "scenario_code"):
            values[field] = str(codes[field])
    elif values["is_new_scenario"] == "否":
        note = "AI 标为已有场景，但这组行业场景名称在码表里没对上，请核对"
        values["remark"] = f"{values['remark']}；{note}" if values["remark"] else note
    return values


async def _save_interpretations(
    run_id: uuid.UUID, tags: list[BaseTag], results: list[dict[str, Any]], codes: dict[str, dict[str, str]]
) -> dict[str, int]:
    written = failed = 0
    async with SessionLocal() as session:
        locked = await repo.base_tags_by_ids(session, [tag.id for tag in tags])
        old = await repo.ai_interpretations(session, [str(tag.source_content_id) for tag in tags])
        plans: list[tuple[BaseTag, list[tuple[str, dict[str, str]]]]] = []
        for index, (snapshot, result) in enumerate(zip(tags, results, strict=True)):
            tag = locked.get(snapshot.id)
            if tag is None or not_run(result):
                continue
            tag.interpreted_at, tag.opportunity_at = utcnow(), None
            if result.get("error") or not result.get("items"):
                failed += 1
                _append_remark(tag, f"{INTERPRET_FAILED}：{str(result.get('error') or '没有解读出内容')[:200]}")
                continue
            rows = old.get(str(tag.source_content_id), [])
            await repo.delete_rows(session, [row for row in rows if untouched(row)])
            planned = []
            for position, item in enumerate(result["items"]):
                values = _row_values(item, codes.get(f"{index}:{position}"))
                planned.append((rules.relation_key(str(tag.source_content_id), values), values))
            plans.append((tag, planned))
        # 先删旧行再写新行：同一个关联主键先删后插，不先落库删除会撞唯一约束。
        await session.flush()
        taken = await repo.taken_relation_keys(session, [key for _, planned in plans for key, _ in planned])
        for tag, planned in plans:
            for key, values in planned:
                if key in taken:
                    continue  # 人工核对过的、手工录入的同一行，或模型重复给了同一行
                taken.add(key)
                session.add(_new_row(tag, values, key))
                written += 1
        await enqueue_event(
            session,
            event_type="policy.ai_tagging.interpreted",
            actor=ROBOT,
            target_id=str(run_id),
            extra={"policies": len(plans) + failed, "rows": written, "failed": failed},
        )
        await session.commit()
    return {"rows": written, "failed": failed}


async def interpret_step(run_id: uuid.UUID, config: PolicyAiTask, spend: Spend) -> str:
    async with SessionLocal() as session:
        tags = await repo.interpret_backlog(session, config.batch_size)
    if not tags:
        return "没有待解读的政策"
    rows = await _prompt_rows(tags, config.content_max_chars)
    await update_run(run_id, stage="interpreting", source_rows=len(tags))
    status, results = await ask(
        run_id,
        spend,
        prompt_id=config.prompt_id,
        rows=rows,
        caller="政策AI打标·政策解读",
        run_field="interpret_run_id",
    )
    counts = await _save_interpretations(run_id, tags, results, await _codes(results))
    await update_run(run_id, interpret_rows=counts["rows"], interpret_failed=counts["failed"])
    left = sum(1 for result in results if not_run(result))
    note = f"{len(tags)} 条政策{reused_note(status)}写入解读 {counts['rows']} 行，解读失败 {counts['failed']} 条"
    if left:
        note += f"；{status.get('error_message') or '任务提前停止'}，{left} 条下批接着解读"
    return note


async def _save_opportunities(run_id: uuid.UUID, tags: list[BaseTag], results: list[dict[str, Any]]) -> dict[str, int]:
    filled = failed = 0
    async with SessionLocal() as session:
        locked = await repo.base_tags_by_ids(session, [tag.id for tag in tags])
        grouped = await repo.ai_interpretations(session, [str(tag.source_content_id) for tag in tags])
        for snapshot, result in zip(tags, results, strict=True):
            tag = locked.get(snapshot.id)
            if tag is None or not_run(result):
                continue
            tag.opportunity_at = utcnow()
            if result.get("error"):
                failed += 1
                _append_remark(tag, f"{OPPORTUNITY_FAILED}：{str(result['error'])[:200]}")
                continue
            rows = grouped.get(str(tag.source_content_id), [])
            matches = rules.match_opportunities(
                result.get("items") or [],
                [{"industry_l1": row.industry_l1, "scenario_l1_name": row.scenario_l1_name} for row in rows],
            )
            if not matches:
                # 钱花了一条也没写回：记成失败，列表上筛得出来，不能悄悄当成补完了。
                failed += 1
                _append_remark(tag, f"{OPPORTUNITY_FAILED}：回答里的行业、场景和这条政策的解读行一条也对不上")
                continue
            for index, text in matches.items():
                row = rows[index]
                if untouched(row):
                    row.market_opportunity = text
                    row.updated_at = row.tagged_at = utcnow()
                    # 有人正在核对页编辑这行（那时市场机会还空着），不加版本号的话他一保存，空值就把这次结果冲掉，
                    # 这行从此算人工改过，也不会再补。
                    row.version += 1
                    filled += 1
        await enqueue_event(
            session,
            event_type="policy.ai_tagging.opportunity",
            actor=ROBOT,
            target_id=str(run_id),
            extra={"policies": len(tags), "rows": filled, "failed": failed},
        )
        await session.commit()
    return {"rows": filled, "failed": failed}


async def opportunity_step(run_id: uuid.UUID, config: PolicyAiTask, spend: Spend) -> str:
    async with SessionLocal() as session:
        tags = await repo.opportunity_backlog(session, config.batch_size)
        grouped = await repo.ai_interpretations(session, [str(tag.source_content_id) for tag in tags])
        rows_by_source = {
            source_id: [{"industry_l1": row.industry_l1, "scenario_l1_name": row.scenario_l1_name} for row in rows]
            for source_id, rows in grouped.items()
        }
        # 解读失败、没有解读行的政策没东西可补，直接记完成，不去问模型。
        empty = [tag for tag in tags if not rows_by_source.get(str(tag.source_content_id))]
        for tag in empty:
            tag.opportunity_at = utcnow()
        await session.commit()
    tags = [tag for tag in tags if rows_by_source.get(str(tag.source_content_id))]
    if not tags:
        return "没有待补市场机会的政策"
    base_rows = await _prompt_rows(tags, config.content_max_chars)
    rows = [
        rules.opportunity_prompt_row(row, rows_by_source[str(tag.source_content_id)])
        for tag, row in zip(tags, base_rows, strict=True)
    ]
    await update_run(run_id, stage="opportunity", source_rows=len(tags))
    status, results = await ask(
        run_id,
        spend,
        prompt_id=config.prompt_id,
        rows=rows,
        caller="政策AI打标·市场机会",
        run_field="opportunity_run_id",
    )
    counts = await _save_opportunities(run_id, tags, results)
    await update_run(run_id, opportunity_rows=counts["rows"], opportunity_failed=counts["failed"])
    left = sum(1 for result in results if not_run(result))
    note = f"{len(tags)} 条政策{reused_note(status)}回填 {counts['rows']} 行，失败 {counts['failed']} 条"
    if left:
        note += f"；{status.get('error_message') or '任务提前停止'}，{left} 条下批接着补"
    return note
