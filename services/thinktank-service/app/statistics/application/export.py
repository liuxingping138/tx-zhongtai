"""智库统计简报 Excel 多工作表导出（总览指标 / 分类分布 / 行为趋势 / 热门文档 / 贡献排行）。"""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from platform_common.actors import Actor
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.statistics.application.statistics import get_statistics_overview
from app.statistics.domain.specs import LibraryScope, StatisticsQuery

_HEADER_FONT = Font(bold=True, color="1E293B")
_HEADER_FILL = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")
_SCOPE_LABEL: dict[LibraryScope, str] = {
    "all": "全部三库",
    "knowledge": "资料库",
    "reports": "报告库",
    "proposals": "方案库",
}


def _write_table(ws: Worksheet, headers: list[str], rows: list[list[Any]]) -> None:
    ws.append(headers)
    for cell in ws[1]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
    for row in rows:
        ws.append(row)
    for idx, header in enumerate(headers, start=1):
        col_letter = get_column_letter(idx)
        width = max(len(str(header)) * 2 + 4, *(min(44, len(str(r[idx - 1])) + 4) for r in rows), 12)
        ws.column_dimensions[col_letter].width = width


def _build_workbook_bytes(data: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws_summary = wb.active or wb.create_sheet("总览指标")
    ws_summary.title = "总览指标"
    assets = data["assets"]
    beh = data["behavior"]
    win = data["window"]
    def_note = f"已定义 {assets['defined_files']} / 未定义 {assets['undefined_files']}"
    lib_rows = [
        [
            f"子库 · {lib['label']}",
            lib["files"],
            f"占比 {lib['share_pct']}% · 存储 {lib['size_display']} · 打标率 {lib['defined_rate']}%",
        ]
        for lib in assets["libraries"]
    ]
    _write_table(
        ws_summary,
        ["指标项", "数值", "补充说明"],
        [
            ["统计时间", data["as_of"], f"库范围：{_SCOPE_LABEL.get(data['library'], data['library'])}"],
            ["统计窗口", f"{win['date_from'] or '全部历史'} 至 {win['date_to']}", f"聚合粒度：{data['granularity']}"],
            ["累计资产总量", assets["total_files"], f"占用存储 {assets['total_size_display']}"],
            ["标签完善率", f"{assets['defined_rate']}%", def_note],
            ["周期新增上传", beh["uploads"], f"标签治理/编辑 {beh['governance']} 次"],
            ["周期在线预览", beh["previews"], f"原文件下载 {beh['downloads']} 次"],
            ["周期活跃人数", beh["active_users"], f"新增收藏 {beh['favorites_added']} 次"],
            ["", "", ""],
            *lib_rows,
        ],
    )

    ws_dim = wb.create_sheet("分类分布")
    dim_rows = [
        [dim["label"], item["name"], item["count"], f"{item['share_pct']}%"]
        for dim in data["dimensions"]
        for item in dim["items"]
    ]
    _write_table(ws_dim, ["统计维度", "分类名称", "文件份数", "占比"], dim_rows)

    ws_trend = wb.create_sheet("行为趋势")
    trend_rows = [
        [
            p["label"],
            p["knowledge_uploads"],
            p["reports_uploads"],
            p["proposals_uploads"],
            p["total_uploads"],
            p["governance"],
            p["previews"],
            p["downloads"],
            p["active_users"],
        ]
        for p in data["trend"]
    ]
    _write_table(
        ws_trend,
        ["周期", "资料库上传", "报告库上传", "方案库上传", "上传合计", "治理/编辑", "预览量", "下载量", "活跃人数"],
        trend_rows,
    )

    ws_docs = wb.create_sheet("热门文档")
    doc_rows = []
    for metric_key, metric_label in (("download", "下载榜"), ("preview", "预览榜"), ("favorite", "收藏榜")):
        for idx, doc in enumerate(data["top_documents"][metric_key], start=1):
            doc_rows.append(
                [
                    metric_label,
                    idx,
                    doc["library_label"],
                    doc["title"],
                    doc["category"],
                    doc["industry"],
                    doc["downloads"],
                    doc["previews"],
                    doc["favorites"],
                    doc["uploader"],
                ]
            )
    _write_table(
        ws_docs,
        ["榜单", "排名", "所属库", "文档名称", "分类", "行业", "下载次数", "预览次数", "收藏数", "上传人"],
        doc_rows,
    )

    ws_people = wb.create_sheet("贡献排行")
    people_rows = [
        ["上传贡献榜", idx, a["name"], a["uploads"], a["governance"], a["previews"], a["downloads"], a["active_days"]]
        for idx, a in enumerate(data["top_contributors"]["upload"], start=1)
    ] + [
        ["高频使用榜", idx, a["name"], a["uploads"], a["governance"], a["previews"], a["downloads"], a["active_days"]]
        for idx, a in enumerate(data["top_contributors"]["active"], start=1)
    ]
    _write_table(
        ws_people,
        ["榜单", "排名", "姓名", "上传份数", "治理次数", "预览次数", "下载次数", "活跃天数"],
        people_rows,
    )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def export_statistics_excel(
    session: AsyncSession,
    *,
    actor: Actor,
    query: StatisticsQuery,
) -> bytes:
    overview = await get_statistics_overview(session, query=query)
    payload = await asyncio.to_thread(_build_workbook_bytes, overview)
    await enqueue_event(
        session,
        event_type="thinktank.statistics.exported",
        actor=actor,
        changes={
            "library": query.library,
            "granularity": query.granularity,
            "preset": query.preset,
            "date_from": query.date_from.isoformat() if query.date_from else None,
            "date_to": query.date_to.isoformat() if query.date_to else None,
        },
    )
    return payload
