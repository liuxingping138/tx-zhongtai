"""政策正文：平台库里不存，点开详情时按源政策 ID 去源库取，提取成看得见的文字给页面。

和打标发给模型的是同一段文字（`rules.clean_content`），业务人员核对打标结果时口径一致。
几百万行正文搬进 policy_db 只为了看要几个 G；源库单条读取实测 0.2 秒，按需读够用。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import anyio
import pymysql
from platform_common.errors import DependencyUnavailableError, NotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import policy_source as source
from app.common import policy_text as rules
from app.policy.domain.models import BaseTag

NO_SOURCE = "这条不是从源库打标的，没有正文"
GONE = "源库里已经找不到这条政策的正文"
SOURCE_DOWN = "源库暂时连不上，正文取不了，稍后再试"
_TITLE_CHUNK = 500
_CONTENT_CHUNK = 200

logger = logging.getLogger("policy.content")


def _safe_http_url(raw: Any) -> str:
    url = str(raw or "").strip()
    return url if url.lower().startswith(("http://", "https://")) else ""


async def _read(func: Any, *args: Any) -> Any:
    try:
        return await anyio.to_thread.run_sync(func, *args)
    except Exception as exc:
        raise DependencyUnavailableError(SOURCE_DOWN) from exc


async def policy_content(source_content_id: str | None) -> dict[str, Any]:
    """{标题, 正文, 原文链接, 出台时间, 字数}。手工录入、导入的行没有源政策 ID，直接说明没有正文。"""

    if not source_content_id:
        raise NotFoundError(NO_SOURCE)
    # 人在页面上等：短超时、不重试（source.read_page），源库出故障二十几秒内回 503，不占着线程几分钟。
    row, html = await _read(source.read_page, source_content_id)
    if row is None or html is None:
        raise NotFoundError(GONE)
    text = rules.clean_content(html, 0)
    return {
        "title": rules.policy_title(row.get("name"))[0],
        "text": text,
        "source_url": _safe_http_url(row.get("original_link")),
        "issued_at": str(row.get("introduced_date") or ""),
        "chars": len(text),
    }


async def policy_contents_by_source_ids(source_content_ids: Sequence[str]) -> dict[str, str]:
    """批量按源政策 ID 读取正文并清洗，返回 {source_content_id: text}。

    分批拉取并即时清洗释放原始 HTML，避免万级导出同时囤积全量富文本撑爆容器内存。
    """

    valid_ids = [cid for cid in dict.fromkeys(source_content_ids) if cid]
    if not valid_ids:
        return {}
    cleaned: dict[str, str] = {}
    for start in range(0, len(valid_ids), _CONTENT_CHUNK):
        batch = valid_ids[start : start + _CONTENT_CHUNK]
        try:
            raw_map: dict[str, str] = await anyio.to_thread.run_sync(source.read_contents, batch)
        except (OSError, pymysql.MySQLError) as exc:
            logger.warning("批量读取源政策正文失败，导出将回退为空正文: %s", exc)
            return cleaned
        for cid, raw_html in raw_map.items():
            if raw_html:
                cleaned[cid] = rules.clean_content(raw_html, 0)
        raw_map.clear()
    return cleaned


async def _lookup_missing_sids(session: AsyncSession, titles: list[str]) -> dict[str, str]:
    title_to_sid: dict[str, str] = {}
    for start in range(0, len(titles), _TITLE_CHUNK):
        chunk = titles[start : start + _TITLE_CHUNK]
        stmt = select(BaseTag.policy_name, BaseTag.source_content_id).where(
            BaseTag.policy_name.in_(chunk), BaseTag.source_content_id.is_not(None)
        )
        res = await session.execute(stmt)
        for name, sid in res.all():
            if sid:
                title_to_sid[name] = str(sid)
    return title_to_sid


async def attach_policy_contents(
    session: AsyncSession,
    items: Sequence[Any],
    rows: list[dict[str, Any]],
) -> None:
    """为导出结果集批量补充「政策正文」列。

    优先使用记录自带的 source_content_id；
    若缺失（如解读表手工/外部导入行），尝试按政策标题回查基础标签表的源 ID。
    """

    id_map: dict[int, str] = {}
    missing_title_indices: list[tuple[int, str]] = []

    for idx, item in enumerate(items):
        sid = getattr(item, "source_content_id", None)
        if sid:
            id_map[idx] = str(sid)
        else:
            title = getattr(item, "policy_title", None) or getattr(item, "policy_name", None)
            if title:
                missing_title_indices.append((idx, str(title)))

    if missing_title_indices:
        titles = list({title for _, title in missing_title_indices})
        title_to_sid = await _lookup_missing_sids(session, titles)
        for idx, title in missing_title_indices:
            if title in title_to_sid:
                id_map[idx] = title_to_sid[title]

    contents = await policy_contents_by_source_ids(list(id_map.values()))
    for idx, row in enumerate(rows):
        sid = id_map.get(idx)
        row["policy_content"] = contents.get(sid, "") if sid else ""
