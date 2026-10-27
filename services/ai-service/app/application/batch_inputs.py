"""批量任务的本次输入：校验上传的 Excel（只解析，不调用模型，不动模板的测试样本），发起时存进任务目录。"""

from __future__ import annotations

from pathlib import PureWindowsPath
from typing import Any

from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import run_excel_parse

from app.application.sheets import rows_workbook, sheet_summary
from app.core import storage
from app.domain.releases import input_columns


def _invalid(message: str) -> ApiError:
    return ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)


async def blank_input(content: str) -> bytes:
    """content 是任务要跑的提示词：只有它引用的列做表头的空白 Excel，和 inspect_upload 按同一份列检查。"""

    columns = input_columns(content)
    if not columns:
        raise _invalid("这个模板不引用任何列，任意 .xlsx 都能上传")
    return await run_excel_parse(rows_workbook, columns, [], "数据")


async def inspect_upload(content: str, upload: tuple[str, bytes]) -> dict[str, Any]:
    """content 是任务要跑的提示词；Excel 必须有它引用的每一列，至少一行数据。"""

    # 浏览器可能带上完整路径（C:\fakepath\a.xlsx）。文件名只用于展示，落盘名固定。
    name = PureWindowsPath(upload[0] or "").name
    if not name.lower().endswith(".xlsx"):
        raise _invalid("批量数据只支持 .xlsx 文件")
    headers, rows = await run_excel_parse(sheet_summary, upload[1])
    missing = [column for column in input_columns(content) if column not in headers]
    if missing:
        raise _invalid(f"这份数据缺少模板引用的列：{'、'.join(missing)}")
    return {"name": name, "rows": rows, "headers": headers}


def snapshot_input(run_id: str, content: bytes) -> None:
    storage.write_atomic(storage.run_dir(run_id) / storage.PROMPT_FILES["excel"], content)
