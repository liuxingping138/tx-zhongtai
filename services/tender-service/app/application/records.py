"""只读列表、详情与按需正文。"""

from datetime import date, datetime

from anyio import to_thread
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from platform_common.excel import build_workbook_async

from app.core.config import get_settings
from app.core.source import Row, source_reader
from app.domain.fields import Kind, Status, export_columns
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
            # 自适应回退：如果指定状态未找到，尝试在另一个状态表中定位
            alt_status: Status = "0" if status == "1" else "1"
            row = records.get_record(reader, kind, alt_status, record_id)
    if row is None:
        raise NotFoundError("未找到该招中标记录，数据状态可能已变化")
    return serialize(row)


def get_content(kind: Kind, status: Status, record_id: int) -> Row:
    with source_reader() as reader:
        row = records.get_record(reader, kind, status, record_id)
        if row is None:
            alt_status: Status = "0" if status == "1" else "1"
            row = records.get_record(reader, kind, alt_status, record_id)
            if row is not None:
                status = alt_status
        if row is None:
            raise NotFoundError("未找到该招中标记录")
        reference = None
        if status == "1":
            # 交付数据若本身有符合 QLM 规范的 content_id，可直接取用；否则反查原始表
            content_id = str(row.get("project_content_id") or "")
            if content_id and len(content_id) <= records.QLM_ID_MAX_LENGTH and content_id.isdecimal():
                reference = row
            else:
                reference = records.original_reference(reader, kind, row) or row
        else:
            reference = row
        content = records.read_content(reader, reference) if reference else None
    if not content:
        raise NotFoundError("未在指定正文表中找到该项目的正文记录")
    if not str(content.get("html") or "").strip():
        raise NotFoundError("已关联到源记录，但正文内容为空")
    return {"html": content["html"]}


def _read_export_rows(kind: Kind, query: ListQuery, limit: int) -> list[Row]:
    with source_reader() as reader:
        return records.export_records(reader, kind, query, limit=limit)


def _format_export_row(row: Row) -> Row:
    formatted = serialize(row)
    formatted["project_status"] = "人工已处理（信息化）" if str(row.get("project_status")) == "1" else "原始数据"
    formatted["is_supp_scene"] = "已补充" if str(row.get("is_supp_scene")) == "1" else "未补充"
    return formatted


async def export_records(kind: Kind, query: ListQuery) -> bytes:
    limit = get_settings().export_max_rows
    rows = await to_thread.run_sync(_read_export_rows, kind, query, limit)
    if len(rows) > limit:
        raise ApiError(
            f"当前筛选结果超过单次导出上限 {limit:,} 条，请先缩小筛选范围（如指定采集日期或省份）后再导出。",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )
    sheet_name = "中标基础数据" if kind == "winbid" else "招标基础数据"
    return await build_workbook_async(
        export_columns(kind),
        [_format_export_row(row) for row in rows],
        sheet_name=sheet_name,
        include_audit=False,
    )
