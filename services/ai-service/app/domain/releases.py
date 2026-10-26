"""模板上线版本和草稿的比较：上线后又改了哪些会影响生产结果的内容。"""

from __future__ import annotations

from typing import Any

from platform_common.clock import format_beijing

from app.domain.categories import category_name
from app.domain.code_tables import code_table_name
from app.domain.models import PromptTemplate, TemplateRelease
from app.domain.templating import CODE_TABLE_FIELD, split_fields, template_variables

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


def input_columns(content: str) -> list[str]:
    """提示词引用的 Excel 列（去重、保持出现顺序），批量任务的输入必须有这些列。"""

    return list(dict.fromkeys(name for name in template_variables(content) if name != CODE_TABLE_FIELD))


def release_summary(
    template: PromptTemplate, release: TemplateRelease | None, model_names: dict[str, str] | None = None
) -> dict[str, Any] | None:
    """模板正在生效的版本。批量任务按它跑，所以把它要哪些列、输出哪些字段、用什么模型和码表一起给出。"""

    if release is None:
        return None
    return {
        "id": release.id,
        "release_no": release.release_no,
        "released_at": format_beijing(release.released_at),
        "released_by_name": release.released_by_name,
        "unreleased_changes": unreleased_changes(template, release),
        "title": release.title,
        "category_name": category_name(release.category),
        "content": release.content,
        "fields": split_fields(release.output_fields),
        "variables": input_columns(release.content),
        "model_id": release.model_id,
        "model_name": (model_names or {}).get(release.model_id, release.model_id),
        "code": code_table_name(release.code_table) if release.code_table else release.code_name,
    }
