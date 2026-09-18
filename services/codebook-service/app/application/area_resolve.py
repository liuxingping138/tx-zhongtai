from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook, load_workbook
from platform_common.errors import ApiError, ErrorCode

from app.application.area_match import AreaSnap, match_area

_ROLE_HEADERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("province_code", ("省份编码", "省编码")),
    ("city_code", ("地市编码", "城市编码")),
    ("district_code", ("区县编码",)),
    ("province_name", ("省份名称", "省份")),
    ("city_name", ("地市名称", "城市名称", "地市", "城市")),
    ("district_name", ("区县名称", "区县")),
)
_CODE_TITLES = {
    "province_code": "省份编码",
    "city_code": "地市编码",
    "district_code": "区县编码",
}
def _header_role(header: str) -> str | None:
    raw = (header or "").replace("\n", " ").strip()
    if not raw:
        return None
    short = raw.split()[0]
    for role, titles in _ROLE_HEADERS:
        for title in titles:
            if raw == title or short == title or raw.startswith(title):
                return role
    return None


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_raw_sheet(content: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("无法读取 Excel 文件", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    sheet = book[book.sheetnames[0]]
    rows = sheet.iter_rows(values_only=True)
    headers: list[str] = []
    for header_row in rows:
        if header_row is None or all(cell is None or str(cell).strip() == "" for cell in header_row):
            continue
        headers = [_cell(cell) for cell in header_row]
        while headers and headers[-1] == "":
            headers.pop()
        break
    else:
        raise ApiError("Excel 为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    items: list[list[str]] = []
    for raw in rows:
        if raw is None or all(cell is None or str(cell).strip() == "" for cell in raw):
            continue
        items.append([_cell(cell) for cell in raw[: len(headers)]])
    return headers, items


def _ensure_code_columns(headers: list[str], roles: list[str | None]) -> tuple[list[str], list[str | None], dict[str, int]]:
    index = {role: idx for idx, role in enumerate(roles) if role}
    next_headers = list(headers)
    next_roles = list(roles)
    for role in ("province_code", "city_code", "district_code"):
        if role in index:
            continue
        index[role] = len(next_headers)
        next_headers.append(_CODE_TITLES[role])
        next_roles.append(role)
    return next_headers, next_roles, index


def _pad(row: list[str], size: int) -> list[str]:
    if len(row) >= size:
        return row[:size]
    return row + [""] * (size - len(row))


def _has_any_code(province_code: str, city_code: str, district_code: str) -> bool:
    return bool(province_code or city_code or district_code)


def build_resolve_workbook(content: bytes, catalog: list[AreaSnap]) -> tuple[bytes, int, int]:
    headers, rows = read_raw_sheet(content)
    roles = [_header_role(header) for header in headers]
    if not any(role in {"province_name", "city_name", "district_name"} for role in roles):
        raise ApiError("未识别到省份/地市/区县列", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    headers, roles, index = _ensure_code_columns(headers, roles)
    annotated: list[tuple[list[str], str]] = []
    matched = 0
    unmatched = 0
    for raw in rows:
        row = _pad(raw, len(headers))
        province = row[index["province_name"]] if "province_name" in index else ""
        city = row[index["city_name"]] if "city_name" in index else ""
        county = row[index["district_name"]] if "district_name" in index else ""
        existing_p = row[index["province_code"]]
        existing_c = row[index["city_code"]]
        existing_d = row[index["district_code"]]
        result = match_area(catalog, province, city, county)
        filled = list(row)
        filled[index["province_code"]] = result.province_code or existing_p
        filled[index["city_code"]] = result.city_code or existing_c
        filled[index["district_code"]] = result.district_code or existing_d
        if _has_any_code(filled[index["province_code"]], filled[index["city_code"]], filled[index["district_code"]]):
            annotated.append((filled, ""))
            matched += 1
        else:
            annotated.append((filled, result.reason or "未关联到省市区编码"))
            unmatched += 1

    book = Workbook()
    sheet = book.active
    sheet.title = "全部数据"
    sheet.append(headers)
    for row, _reason in annotated:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue(), matched, unmatched
