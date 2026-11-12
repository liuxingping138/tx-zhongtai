"""只读列表、详情与按需正文。"""

from datetime import date, datetime

from platform_common.errors import NotFoundError

from app.core.source import Row, source_reader
from app.domain.fields import Kind, Status
from app.domain.queries import ListQuery
from app.repositories import records


def serialize(row: Row) -> Row:
    result = dict(row)
    # 源库雪花 ID 超出 JS 安全整数范围，必须在 JSON 编码前转字符串。
    result["id"] = str(row["id"])
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat(sep=" ")
        elif isinstance(value, date):
            result[key] = value.isoformat()
    return result


def list_records(kind: Kind, query: ListQuery) -> Row:
    with source_reader() as reader:
        rows = records.list_records(reader, kind, query)
    return {
        "items": [serialize(row) for row in rows[: query.page_size]],
        "has_more": len(rows) > query.page_size,
        "page": query.page,
        "page_size": query.page_size,
    }


def get_record(kind: Kind, status: Status, record_id: int) -> Row:
    with source_reader() as reader:
        row = records.get_record(reader, kind, status, record_id)
    if row is None:
        raise NotFoundError("未找到该招中标记录，数据状态可能已变化")
    return serialize(row)


def get_content(kind: Kind, status: Status, record_id: int) -> Row:
    with source_reader() as reader:
        row = records.get_record(reader, kind, status, record_id)
        if row is None:
            raise NotFoundError("未找到该招中标记录")
        reference = records.original_reference(reader, kind, row) if status == "1" else row
        content = records.read_content(reader, reference) if reference else None
    if not content:
        raise NotFoundError("未在指定正文表中找到该项目的正文记录")
    if not str(content.get("html") or "").strip():
        raise NotFoundError("已关联到源记录，但正文内容为空")
    return {"html": content["html"]}
