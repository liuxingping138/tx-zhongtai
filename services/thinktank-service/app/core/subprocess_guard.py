"""处理上传文档的外部命令（LibreOffice、Ghostscript、qpdf）共用的进程隔离。

- 单开进程组（`start_new_session=True`），超时、请求取消都整组杀掉：soffice 的真正干活的是孙进程，
  gs 也可能被卡在一个畸形文档上，只杀直接子进程会留下孤儿。
- 子进程只拿最少的环境变量，不把数据库口令、对象存储密钥、内部调用密钥交给处理不可信文档的进程。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from pathlib import Path

from platform_common.logging_setup import get_logger

logger = get_logger(__name__)

CHILD_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "TZ")
_STDERR_LOG_CHARS = 400


def child_env(home: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in CHILD_ENV_KEYS if key in os.environ}
    env["HOME"] = str(home)
    return env


async def kill_group(proc: asyncio.subprocess.Process) -> None:
    """整组发 SIGKILL 并等它退出。

    壳进程退出了，同组的孙进程也可能还在，所以不看 returncode，整组都发；组里没人了就是 ProcessLookupError。
    """

    if sys.platform != "win32":  # 只在 Linux 容器里跑；Windows 上跑单测时没有进程组
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
    # 不等它退出就会留下僵尸；被取消时也要等完，所以屏蔽取消。
    await asyncio.shield(proc.wait())


async def run_isolated(args: list[str], *, home: Path, timeout_seconds: float, label: str) -> int | None:
    """在独立进程组里跑一条命令，返回退出码；超时返回 None。结束（含被取消）后整组清掉。"""

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        env=child_env(home),
        start_new_session=True,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("subprocess_timeout", tool=label, timeout_seconds=timeout_seconds)
        return None
    finally:
        await kill_group(proc)
    if proc.returncode != 0:
        logger.warning(
            "subprocess_failed",
            tool=label,
            returncode=proc.returncode,
            stderr=(stderr or b"").decode("utf-8", "ignore")[:_STDERR_LOG_CHARS],
        )
    return proc.returncode
