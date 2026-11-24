"""预览转码、压缩共用的名额：Office 转 PDF（soffice + gs + qpdf）和 PDF 压缩线性化（gs + qpdf）
合计同时最多 `MAX_JOBS` 个。

两条流水线原来各有 2 个名额，同时可能起 4 个 soffice / gs，加上服务进程本身会撑破 `THINKTANK_MEM_LIMIT`（1536m），
被 OOM 杀掉时整个服务重启、所有在途请求一起失败。一个任务里的外部命令是一条接一条跑的，
所以合计名额也就是同时最多几个重进程。

上传后的预热不和正在看的人抢：`hold(wait=False)` 在拿名额的那一刻名额已满就抛 `SlotBusyError`，
检查和拿名额之间没有 await，不会出现「检查时有空、排上队时已经满了」。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

MAX_JOBS = 2
_SEMAPHORE = asyncio.Semaphore(MAX_JOBS)


class SlotBusyError(RuntimeError):
    """名额已满，调用方要求不排队（上传后的预热）。"""


def has_free_slot() -> bool:
    return not _SEMAPHORE.locked()


@contextlib.asynccontextmanager
async def hold(*, wait: bool = True) -> AsyncIterator[None]:
    """拿一个名额；`wait=False` 时名额已满立即抛 SlotBusyError，不排队。"""

    # Semaphore 没满时 acquire 不让出事件循环：这里的检查和下面拿名额是同一步完成的。
    if not wait and _SEMAPHORE.locked():
        raise SlotBusyError
    async with _SEMAPHORE:
        yield
