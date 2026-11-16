"""类型判断写基础标签的几种落法：新建或更新 AI 行、判成重复副本、这次没问成。不碰库连接，调用方给会话、负责提交。"""

from __future__ import annotations

from typing import Any

from platform_common.clock import utcnow

from app.aitag.application.pipeline import ROBOT
from app.aitag.domain import rules
from app.policy.domain.fields import TYPE_NOTES
from app.policy.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash


def write(
    session: Any,
    existing: BaseTag | None,
    source_row: dict[str, Any],
    values: dict[str, str],
    *,
    force: bool = False,
    ai_outputs: dict[str, str] | None = None,
) -> bool:
    """有这条政策的 AI 行就更新，返回是否写入。

    人工在打标之后改过的不覆盖，除非是人在列表上点了「重新判断类型」（force）。
    """

    now = utcnow()
    if existing is not None:
        if not force and existing.tagged_at is not None and existing.updated_at > existing.tagged_at:
            return False
        existing.type_retag_at = None
        # 只有类型或「是否解读」变了，后面两步才按新类型重做：用新模板重判一千条类型没变的政策，
        # 不能把最贵的解读整批重跑一遍。
        changed = rules.redoes_downstream(existing, values)
        for key, value in values.items():
            setattr(existing, key, value)
        if ai_outputs is not None:
            existing.ai_outputs = dict(ai_outputs)
        existing.refresh_hash()
        existing.version += 1
        existing.tagged_at = existing.updated_at = now
        if changed:
            existing.interpreted_at = existing.opportunity_at = None
        existing.updated_by_id, existing.updated_by_name = ROBOT.id, ROBOT.name
        return True
    session.add(
        BaseTag(
            content_hash=content_hash(values, BASE_TAG_FIELDS),
            source_content_id=str(source_row["content_id"]),
            ai_outputs=dict(ai_outputs or {}),
            tagged_at=now,
            version=1,
            created_at=now,
            created_by_id=ROBOT.id,
            created_by_name=ROBOT.name,
            updated_at=now,
            updated_by_id=ROBOT.id,
            updated_by_name=ROBOT.name,
            **values,
        )
    )
    return True


def note_duplicate(row: BaseTag) -> None:
    """重打后和另一条内容一样：出队、备注注明，不动其他字段。"""

    row.type_retag_at = None
    row.remark = rules.note_duplicate(row.remark, str(row.source_content_id))
    row.refresh_hash()
    row.version += 1
    row.tagged_at = row.updated_at = utcnow()
    row.updated_by_id, row.updated_by_name = ROBOT.id, ROBOT.name


def note_retag_failed(row: BaseTag, note: str) -> None:
    """重新判断类型这次没问成：出队，备注换上这次的失败说明，类型、解读都不动。

    不重算内容哈希：同一网页的几条副本失败原因一样，加上同一句说明会变得一模一样、撞唯一约束整批回滚。
    """

    row.type_retag_at = None
    kept = rules.drop_notes(row.remark, TYPE_NOTES)
    row.remark = rules.NOTE_SEP.join(part for part in (f"{note}（保留了上次的类型）", kept) if part)
    row.version += 1
    row.tagged_at = row.updated_at = utcnow()
    row.updated_by_id, row.updated_by_name = ROBOT.id, ROBOT.name
