"""政策正文：平台库里不存，点开详情时按源政策 ID 去源库取，提取成看得见的文字给页面。

和打标发给模型的是同一段文字（`rules.clean_content`），业务人员核对打标结果时口径一致。
几百万行正文搬进 policy_db 只为了看要几个 G；源库单条读取实测 0.2 秒，按需读够用。
"""

from __future__ import annotations

from typing import Any

import anyio
from platform_common.errors import DependencyUnavailableError, NotFoundError

from app.aitag.domain import rules
from app.aitag.repositories import source

NO_SOURCE = "这条不是从源库打标的，没有正文"
GONE = "源库里已经找不到这条政策的正文"
SOURCE_DOWN = "源库暂时连不上，正文取不了，稍后再试"


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
        "source_url": str(row.get("original_link") or ""),
        "issued_at": str(row.get("introduced_date") or ""),
        "chars": len(text),
    }
