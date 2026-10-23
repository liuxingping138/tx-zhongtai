"""直接写出只有文本的 xlsx，给业务表导出用。

openpyxl 每个单元格建一个对象再序列化，2 万行信源导出要 3.3 秒；导出只有纯文本、不要样式，
直接拼工作表 XML 只要 0.5 秒，读回来内容一致。

单元格一律写成内联字符串（inlineStr）：Excel 不会把它当公式，``=HYPERLINK(...)`` 之类导出后仍是文本。
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterable, Sequence
from io import BytesIO
from xml.sax.saxutils import escape, quoteattr

from openpyxl.utils.cell import get_column_letter

# XML 1.0 不允许的字符：openpyxl 遇到会直接报错，整次导出失败。爬来的数据里偶尔夹带，去掉。
_ILLEGAL_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
# \r 不转义的话 XML 解析时会被规范成 \n，导出再导回来就变了。
_ENTITIES = {"\r": "&#13;"}
# Excel 工作表名不能有这些字符，最长 31 个字。
_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
# 每攒这么多行往压缩流里写一次，大表导出不用把整张表的 XML 先拼在内存里。
_CHUNK_ROWS = 1000
# 固定时间戳：同样的数据每次生成的文件字节一致。
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)

_XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES = (
    _XML_HEAD + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    "</Types>"
)
_ROOT_RELS = (
    _XML_HEAD + f'<Relationships xmlns="{_PKG_REL_NS}">'
    f'<Relationship Id="rId1" Type="{_REL_NS}/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)
_WORKBOOK_RELS = (
    _XML_HEAD + f'<Relationships xmlns="{_PKG_REL_NS}">'
    f'<Relationship Id="rId1" Type="{_REL_NS}/worksheet" Target="worksheets/sheet1.xml"/>'
    f'<Relationship Id="rId2" Type="{_REL_NS}/styles" Target="styles.xml"/>'
    "</Relationships>"
)
# 最小样式表：没有它 Excel 能打开，但部分软件（WPS 旧版、Numbers）会提示文件损坏。
_STYLES = (
    _XML_HEAD + f'<styleSheet xmlns="{_MAIN_NS}">'
    '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)


def sheet_title(name: str) -> str:
    return _BAD_SHEET_CHARS.sub("_", name)[:31] or "Sheet1"


def _workbook(title: str) -> str:
    return (
        _XML_HEAD + f'<workbook xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}">'
        f'<sheets><sheet name={quoteattr(title)} sheetId="1" r:id="rId1"/></sheets></workbook>'
    )


def _row_xml(number: int, letters: Sequence[str], values: Sequence[str]) -> str:
    cells = [
        f'<c r="{letter}{number}" t="inlineStr"><is><t xml:space="preserve">'
        f"{escape(_ILLEGAL_XML.sub('', value), _ENTITIES)}</t></is></c>"
        for letter, value in zip(letters, values, strict=False)
        if value
    ]
    return f'<row r="{number}">{"".join(cells)}</row>'


def write_text_xlsx(sheet_name: str, rows: Iterable[Sequence[str]], *, column_count: int) -> bytes:
    """一张工作表，每行是一组字符串，空串不写单元格。"""

    letters = [get_column_letter(index) for index in range(1, column_count + 1)]
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as book:
        for path, text in (
            ("[Content_Types].xml", _CONTENT_TYPES),
            ("_rels/.rels", _ROOT_RELS),
            ("xl/workbook.xml", _workbook(sheet_title(sheet_name))),
            ("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS),
            ("xl/styles.xml", _STYLES),
        ):
            book.writestr(_entry(path), text)
        with book.open(_entry("xl/worksheets/sheet1.xml"), "w") as sheet:
            sheet.write(f'{_XML_HEAD}<worksheet xmlns="{_MAIN_NS}"><sheetData>'.encode())
            chunk: list[str] = []
            for number, values in enumerate(rows, start=1):
                chunk.append(_row_xml(number, letters, values))
                if len(chunk) >= _CHUNK_ROWS:
                    sheet.write(_encode(chunk))
                    chunk = []
            sheet.write(_encode(chunk))
            sheet.write(b"</sheetData></worksheet>")
    return buffer.getvalue()


def _entry(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _encode(chunk: list[str]) -> bytes:
    # 落单的代理字符（源数据编码坏了）无法编成 UTF-8，换成问号，不让整次导出失败。
    return "".join(chunk).encode("utf-8", "replace")
