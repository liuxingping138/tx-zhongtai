"""打标的后两步，按待办做：

2. 政策解读：基础标签里「是否解读 = 是」、还没解读的政策 → 用上线模板解读 → 一条政策展开成多行写进政策解读表。
3. 市场机会：解读过、还没做市场机会的政策 → 用上线模板写市场机会 → 按一级行业 + 一级场景回填到它的解读行。

费用到上限没轮到的政策不记进度，下一批接着做。AI 写的行只要人工核对过（人工验证）或改过，就不再覆盖。
"""

from __future__ import annotations

import logging
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
from app.policy.application import scenario_engine
from app.policy.domain.fields import DATA_STATUS_PENDING, POLICY_TITLE_MAX
from app.policy.domain.models import BaseTag, Interpretation

logger = logging.getLogger("policy.aitag.interpreting")


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


def _new_row(
    tag: BaseTag, values: dict[str, str], key: str, ai_outputs: dict[str, str] | None = None
) -> Interpretation:
    now = utcnow()
    return Interpretation(
        record_id=str(uuid.uuid4()),
        tenant_id="",
        policy_uid=str(tag.source_content_id)[: rules.UID_MAX],
        policy_title=tag.policy_name[:POLICY_TITLE_MAX],
        relation_key=key,
        source_content_id=str(tag.source_content_id),
        tagged_at=now,
        data_status=DATA_STATUS_PENDING,
        market_opportunity="",
        ai_outputs=dict(ai_outputs or {}),
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
    stale: set[uuid.UUID] = set()
    async with SessionLocal() as session:
        locked = await repo.base_tags_by_ids(session, [tag.id for tag in tags])
        old = await repo.ai_interpretations(session, [str(tag.source_content_id) for tag in tags])
        plans: list[tuple[BaseTag, list[tuple[str, dict[str, str], dict[str, str]]]]] = []
        for index, (snapshot, result) in enumerate(zip(tags, results, strict=True)):
            tag = locked.get(snapshot.id)
            if tag is None or not_run(result):
                continue
            tag.interpreted_at, tag.opportunity_at = utcnow(), None
            if result.get("error") or not result.get("items"):
                failed += 1
                _append_remark(tag, f"{INTERPRET_FAILED}：{str(result.get('error') or '没有解读出内容')[:200]}")
                continue
            rows = [row for row in old.get(str(tag.source_content_id), []) if untouched(row)]
            stale.update(row.candidate_id for row in rows if row.candidate_id)
            await repo.delete_rows(session, rows)
            planned = []
            for position, item in enumerate(result["items"]):
                values = _row_values(item, codes.get(f"{index}:{position}"))
                planned.append(
                    (rules.relation_key(str(tag.source_content_id), values), values, rules.extract_ai_outputs(item))
                )
            plans.append((tag, planned))
        # 先删旧行再写新行：同一个关联主键先删后插，不先落库删除会撞唯一约束。
        await session.flush()
        await scenario_engine.recount(session, stale)  # 旧行删掉了，它们归属的候选少了几行
        taken = await repo.taken_relation_keys(session, [key for _, planned in plans for key, _, _ in planned])
        for tag, planned in plans:
            for key, values, extra in planned:
                if key in taken:
                    continue  # 人工核对过的、手工录入的同一行，或模型重复给了同一行
                taken.add(key)
                session.add(_new_row(tag, values, key, extra))
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


async def _classify_new_rows() -> None:
    """刚写进去的行和码表比对、归到新增场景候选。比对出错不影响已写入的解读，下一批或补数时接着比。"""

    try:
        await scenario_engine.classify_backlog()
    except Exception:  # 比对失败不该让这批解读记成失败，行留着「还没比对」下次补
        logger.exception("解读行和码表比对失败，下次补比对")


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
    await _classify_new_rows()
    await update_run(run_id, interpret_rows=counts["rows"], interpret_failed=counts["failed"])
    left = sum(1 for result in results if not_run(result))
    note = f"{len(tags)} 条政策{reused_note(status)}写入解读 {counts['rows']} 行，解读失败 {counts['failed']} 条"
    if left:
        note += f"；{status.get('error_message') or '任务提前停止'}，{left} 条下批接着解读"
    return note


async def _save_opportunities(
    run_id: uuid.UUID,
    tags: list[BaseTag],
    plans: list[tuple[BaseTag, str, str]],
    results: list[dict[str, Any]],
) -> dict[str, int]:
    filled = failed = 0
    by_tag: dict[uuid.UUID, list[tuple[str, str, dict[str, Any]]]] = {}
    for (snapshot, industry, scene), result in zip(plans, results, strict=True):
        by_tag.setdefault(snapshot.id, []).append((industry, scene, result))
    async with SessionLocal() as session:
        locked = await repo.base_tags_by_ids(session, [tag.id for tag in tags])
        grouped = await repo.ai_interpretations(session, [str(tag.source_content_id) for tag in tags])
        for snapshot in tags:
            tag = locked.get(snapshot.id)
            entries = by_tag.get(snapshot.id, [])
            if tag is None or not entries or any(not_run(result) for _, _, result in entries):
                continue
            tag.opportunity_at = utcnow()
            rows = grouped.get(str(tag.source_content_id), [])
            errors: list[str] = []
            for industry, scene, result in entries:
                if result.get("error"):
                    errors.append(f"{industry}/{scene}：{str(result['error'])[:120]}")
                    continue
                text = rules.extract_opportunity_text(result.get("items") or [], industry, scene)
                if not text:
                    errors.append(f"{industry}/{scene}：没有返回市场机会")
                    continue
                for row in rows:
                    if row.industry_l1 == industry and row.scenario_l1_name == scene and untouched(row):
                        row.market_opportunity = text
                        row.updated_at = row.tagged_at = utcnow()
                        # 有人正在核对页编辑这行（那时市场机会还空着），不加版本号的话他一保存，空值就把这次结果冲掉，
                        # 这行从此算人工改过，也不会再补。
                        row.version += 1
                        filled += 1
            if errors:
                failed += 1
                _append_remark(tag, f"{OPPORTUNITY_FAILED}：{'；'.join(errors)[:200]}")
        await enqueue_event(
            session,
            event_type="policy.ai_tagging.opportunity",
            actor=ROBOT,
            target_id=str(run_id),
            extra={"policies": len(tags), "groups": len(plans), "rows": filled, "failed": failed},
        )
        await session.commit()
    return {"rows": filled, "failed": failed}


async def opportunity_step(run_id: uuid.UUID, config: PolicyAiTask, spend: Spend) -> str:
    async with SessionLocal() as session:
        tags = await repo.opportunity_backlog(session, config.batch_size)
        grouped = await repo.ai_interpretations(session, [str(tag.source_content_id) for tag in tags])
        rows_by_source = {
            source_id: [
                {"industry_l1": row.industry_l1, "scenario_l1_name": row.scenario_l1_name}
                for row in rows
                if untouched(row)
            ]
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
    plans: list[tuple[BaseTag, str, str]] = []
    rows: list[dict[str, str]] = []
    for tag, base_row in zip(tags, base_rows, strict=True):
        for (industry, scene), prompt_row in rules.opportunity_prompt_rows(
            base_row, rows_by_source[str(tag.source_content_id)]
        ):
            plans.append((tag, industry, scene))
            rows.append(prompt_row)
    await update_run(run_id, stage="opportunity", source_rows=len(rows))
    status, results = await ask(
        run_id,
        spend,
        prompt_id=config.prompt_id,
        rows=rows,
        caller="政策AI打标·市场机会",
        run_field="opportunity_run_id",
    )
    counts = await _save_opportunities(run_id, tags, plans, results)
    await update_run(run_id, opportunity_rows=counts["rows"], opportunity_failed=counts["failed"])
    unfinished = {tag.id for (tag, _, _), result in zip(plans, results, strict=True) if not_run(result)}
    note = (
        f"{len(tags)} 条政策（{len(rows)} 组行业场景）{reused_note(status)}"
        f"回填 {counts['rows']} 行，失败 {counts['failed']} 条"
    )
    if unfinished:
        note += f"；{status.get('error_message') or '任务提前停止'}，{len(unfinished)} 条下批接着补"
    return note
