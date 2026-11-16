"""在政策基础标签列表上勾选政策「重新打标」：打失败的、或模板改好后想按新模板重打的。

只是把这些政策放回对应任务的待办，不当场调模型；下次执行那个任务（手动或每日计划）时处理，费用照常记在那个任务上。

- 重新判断类型：记下请求时间，类型判断下一批先按源政策 ID 重读重打这些，覆盖原来的类型
  （人工改过也覆盖，是人点名要重打的）。已经在排队的再点一次不重记时间，不会挪到队尾。
- 重新解读：清掉解读和市场机会的完成时间，回到解读待办；人工验证过的解读行照样不覆盖。
- 重新补市场机会：清掉市场机会完成时间，回到市场机会待办。
旧的失败说明从备注里去掉：列表上马上显示「等待重新判断类型」而不是还挂着失败，重打成功了也不会留着上次的原因。
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.errors import ApiError, ErrorCode
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.domain.rules import DUPLICATE_NOTE, INTERPRET_FAILED, MISSING_NOTE, OPPORTUNITY_FAILED, drop_notes
from app.aitag.domain.tasks import TASKS
from app.aitag.repositories import source
from app.aitag.repositories import tagging as repo
from app.common.audit_emit import enqueue_event
from app.core.database import SessionLocal
from app.policy.domain.fields import TYPE_NOTES
from app.policy.domain.models import BaseTag

BATCH_MAX = 500
# 放回各任务待办时去掉的旧说明。类型判断连上次重判留下的「和另一条相同」「源库找不到」一起去掉：这次会重新判断。
_STEP_NOTES = {
    "type": (*TYPE_NOTES, DUPLICATE_NOTE, MISSING_NOTE),
    "interpret": (INTERPRET_FAILED, OPPORTUNITY_FAILED),
    "opportunity": (OPPORTUNITY_FAILED,),
}


def _skip_reason(tag: BaseTag, step: str) -> str | None:
    if not tag.source_content_id:
        return "手工录入或导入的政策没有源政策，不能重新打标"
    if step == "interpret" and tag.need_interpret != "是":
        return "「是否解读」不是「是」，先重新判断类型或把它改成「是」"
    if step == "opportunity" and tag.interpreted_at is None:
        return "还没解读，先重新解读"
    return None


def _queue(tag: BaseTag, step: str) -> bool:
    """放回待办，返回这一行有没有变（已经在待办里、也没有旧说明可去的不变）。"""

    before = (tag.type_retag_at, tag.interpreted_at, tag.opportunity_at, tag.remark)
    if step == "type":
        # 已经在排队的保留原来的时间：再点一次不该挪到队尾。
        tag.type_retag_at = tag.type_retag_at or utcnow()
    else:
        tag.opportunity_at = None
        if step == "interpret":
            tag.interpreted_at = None
    tag.remark = drop_notes(tag.remark, _STEP_NOTES[step])
    return (tag.type_retag_at, tag.interpreted_at, tag.opportunity_at, tag.remark) != before


async def _resolve_tags(
    session: AsyncSession, item_ids: list[uuid.UUID], skipped: Counter[str]
) -> tuple[dict[uuid.UUID, BaseTag], int]:
    tags = await repo.base_tags_by_ids(session, list(item_ids))
    unresolved = [uid for uid in dict.fromkeys(item_ids) if uid not in tags]
    if not unresolved or session is None:
        return tags, len(unresolved)
    interps = await repo.interpretations_by_ids(session, unresolved)
    missing = len(unresolved) - len(interps)
    source_ids: list[str] = []
    for interp in interps.values():
        if not interp.source_content_id:
            skipped["手工录入或导入的政策没有源政策，不能重新打标"] += 1
        else:
            source_ids.append(str(interp.source_content_id))
    for tag in await repo.base_tags_by_source_ids(session, list(dict.fromkeys(source_ids))):
        tags[tag.id] = tag
    return tags, missing


async def request(session: AsyncSession, actor: Actor, item_ids: list[uuid.UUID], step: str) -> dict[str, Any]:
    """把勾选的政策（或政策解读行所属的政策）放回某个任务的待办。返回放回几条、跳过的各是什么原因。"""

    if step not in TASKS:
        raise ApiError("不认识的打标步骤", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    skipped: Counter[str] = Counter()
    tags, missing = await _resolve_tags(session, list(item_ids), skipped)
    queued = []
    for tag in tags.values():
        reason = _skip_reason(tag, step)
        if reason:
            skipped[reason] += 1
            continue
        # 不改更新时间：「人工改过的 AI 行不覆盖」看的是更新时间，排个队不算人工改。
        # 改了的版本号照常加，防止并发编辑写回旧备注；本来就在待办里的不动，不让正在编辑的人白白撞版本冲突。
        if _queue(tag, step):
            tag.version += 1
        queued.append(tag)
    if missing:
        skipped["政策已被删除"] += missing
    if queued:
        await enqueue_event(
            session,
            event_type="policy.ai_tagging.retag_requested",
            actor=actor,
            target_id=str(queued[0].id) if len(queued) == 1 else "batch",
            changes={"step": TASKS[step], "rows": len(queued)},
            extra={"source_ids": [tag.source_content_id for tag in queued][:BATCH_MAX]},
        )
    return {
        "step": step,
        "task": TASKS[step],
        "queued": len(queued),
        "skipped": [{"reason": reason, "count": count} for reason, count in skipped.most_common()],
    }


async def type_queue(limit: int) -> list[str]:
    """等着重新判断类型的源政策 ID，先点的先打。"""

    async with SessionLocal() as session:
        return [str(tag.source_content_id) for tag in await repo.type_retag_queue(session, limit)]


async def read_queued(source_ids: list[str]) -> tuple[list[dict[str, Any]], int]:
    """按 ID 去源库重读排队的政策。源库里已经没有的清掉排队标记、备注写明，免得每批都卡在它们身上。"""

    rows = await anyio.to_thread.run_sync(source.read_by_ids, source_ids)
    found = {str(row["content_id"]) for row in rows}
    missing = [source_id for source_id in source_ids if source_id not in found]
    if missing:
        async with SessionLocal() as session:
            for tag in await repo.base_tags_by_source_ids(session, missing):
                tag.type_retag_at = None
                tag.remark = drop_notes(tag.remark, (MISSING_NOTE,))
                tag.remark = f"{tag.remark}；{MISSING_NOTE}" if tag.remark else MISSING_NOTE
                tag.version += 1
            await session.commit()
    return rows, len(missing)
