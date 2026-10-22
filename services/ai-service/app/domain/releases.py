"""模板上线版本和草稿的比较：上线后又改了哪些会影响生产结果的内容。"""

from __future__ import annotations

from typing import Any

from platform_common.clock import format_beijing

from app.domain.models import PromptTemplate, TemplateRelease

# 只比这些：上传测试 Excel、改附件名不影响定时任务的结果。
RELEASED_FIELDS = ("title", "category", "content", "output_fields", "model_id", "code_table")
FIELD_NAMES = {
    "title": "标题",
    "category": "类型",
    "content": "提示词内容",
    "output_fields": "输出字段",
    "model_id": "模型",
    "code_table": "码表",
}


def unreleased_changes(template: PromptTemplate, release: TemplateRelease) -> list[str]:
    changed = [field for field in RELEASED_FIELDS if getattr(template, field) != getattr(release, field)]
    # 用上传码表的模板，换了码表文件也算改动（文件内容在上线时已复制冻结）。
    if not template.code_table and template.code_name != release.code_name and "code_table" not in changed:
        changed.append("code_table")
    return [FIELD_NAMES[field] for field in changed]


def release_summary(template: PromptTemplate, release: TemplateRelease | None) -> dict[str, Any] | None:
    if release is None:
        return None
    return {
        "id": release.id,
        "release_no": release.release_no,
        "released_at": format_beijing(release.released_at),
        "released_by_name": release.released_by_name,
        "unreleased_changes": unreleased_changes(template, release),
    }
