"""执行一个批量任务，由 worker 调用。

N 个协程从同一个队列取行并发提问；每完成一行立即追加到原始返回 CSV，进程中途被杀也保留已跑结果。
另一个协程定时写进度和心跳，并检查停止标志：置位后不再取新行，等在途请求返回后收尾。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import anyio
import httpx
from platform_common.clock import utcnow
from platform_common.excel import run_excel_parse

from app.application.asking import llm_request
from app.application.batch_output import (
    RowResult,
    append_log,
    append_raw,
    build_result,
    start_raw,
    write_failed,
)
from app.application.sheets import read_sheet
from app.core import storage
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.llm import stream_responses
from app.domain.llm_models import LlmModel, build_body, calc_costs, find_model
from app.domain.models import RUN_CANCELLED, RUN_DONE, RUN_FAILED, RUN_INTERRUPTED, BatchRun
from app.domain.templating import build_myid, fill_template, split_fields
from app.repositories import batch_runs as repo

logger = logging.getLogger("ai.batch")
PROGRESS_SECONDS = 2.0
ERROR_MAX = 2000


@dataclass
class Job:
    run: BatchRun
    model: LlmModel
    headers: list[str]
    rows: list[dict[str, str]]
    prompts: deque[tuple[str, str]]
    results: dict[str, RowResult] = field(default_factory=dict)
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    input_tokens: int = 0
    output_tokens: int = 0
    search_calls: int = 0
    failed: int = 0

    def path(self, kind: str) -> Any:
        return storage.run_file(self.run.id, kind)


async def call_model_once(model: LlmModel, prompt: str, thinking: bool, client: httpx.AsyncClient) -> RowResult:
    """消费整条流，只要最终文本、用量、错误和联网次数。联网次数优先用 usage 里的权威值，没有就数进度事件。"""

    started = time.monotonic()
    parts: list[str] = []
    usage: dict[str, int] = {}
    errors: list[str] = []
    search_events = 0
    async for event in stream_responses(llm_request(model, build_body(model, prompt, thinking=thinking)), client):
        if "text" in event:
            parts.append(event["text"])
        elif "usage" in event:
            usage = event["usage"]
        elif "error" in event:
            errors.append(event["error"])
        elif event.get("tool_event", {}).get("stage") == "web_search_in_progress":
            search_events += 1
    return RowResult(
        myid="",
        prompt=prompt,
        text="".join(parts),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        search_calls=usage.get("web_search", search_events),
        error=errors[-1] if errors else "",
        elapsed=round(time.monotonic() - started, 2),
    )


def _log(job: Job, message: str) -> None:
    stamp = utcnow().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    append_log(job.path("log"), f"{stamp} {message}")


async def _record(job: Job, result: RowResult) -> None:
    job.results[result.myid] = result
    job.input_tokens += result.input_tokens
    job.output_tokens += result.output_tokens
    job.search_calls += result.search_calls
    done = len(job.results)
    if result.error:
        job.failed += 1
        line = f"[{done}/{len(job.rows)}] {result.myid} 失败 耗时={result.elapsed}s 错误={result.error}"
    else:
        line = f"[{done}/{len(job.rows)}] {result.myid} 成功 耗时={result.elapsed}s"
    await anyio.to_thread.run_sync(append_raw, job.path("raw"), result.raw_row(job.model.name))
    await anyio.to_thread.run_sync(_log, job, line)


async def _consume(job: Job, client: httpx.AsyncClient) -> None:
    while job.prompts and not job.stop.is_set():
        myid, prompt = job.prompts.popleft()
        result = await call_model_once(job.model, prompt, job.run.thinking, client)
        result.myid = myid
        await _record(job, result)


def _progress(job: Job) -> dict[str, Any]:
    return {
        "done_count": len(job.results),
        "failed_count": job.failed,
        "input_tokens": job.input_tokens,
        "output_tokens": job.output_tokens,
        "search_calls": job.search_calls,
        "heartbeat_at": utcnow(),
    }


async def _watch(job: Job) -> None:
    """写进度和心跳；发现停止标志就让取行协程停手。"""

    while True:
        await asyncio.sleep(PROGRESS_SECONDS)
        async with SessionLocal() as session:
            await repo.update_fields(session, job.run.id, _progress(job))
            if await repo.cancel_flag(session, job.run.id):
                job.stop.set()
            await session.commit()


async def _load(run: BatchRun) -> Job:
    model = find_model(run.model_id)
    if model is None:
        raise RuntimeError(f"未知模型：{run.model_id}")
    excel = storage.run_dir(run.id) / storage.PROMPT_FILES["excel"]
    if not await anyio.Path(excel).is_file():
        raise RuntimeError("任务的 Excel 快照不存在")
    content = await anyio.Path(excel).read_bytes()
    headers, rows = await run_excel_parse(read_sheet, content)
    if run.row_limit > 0:
        rows = rows[: run.row_limit]
    if not rows:
        raise RuntimeError("Excel 没有数据行")
    code = storage.run_dir(run.id) / storage.PROMPT_FILES["code"]
    code_text = await anyio.Path(code).read_text(encoding="utf-8") if await anyio.Path(code).is_file() else ""
    for index, row in enumerate(rows):
        row["myid"] = build_myid(index)
    prompts = deque((row["myid"], fill_template(run.prompt_content, row, code_text)) for row in rows)
    return Job(run=run, model=model, headers=headers, rows=rows, prompts=prompts)


async def _finish(job: Job, status: str, message: str = "") -> None:
    if job.results:
        await anyio.to_thread.run_sync(
            build_result,
            job.path("result"),
            job.headers,
            job.rows,
            job.results,
            split_fields(job.run.output_fields),
            job.model.name,
        )
    failed = [item for item in job.results.values() if item.error]
    if failed:
        await anyio.to_thread.run_sync(write_failed, job.path("failed"), failed)
    inference, search = calc_costs(job.model.id, job.input_tokens, job.output_tokens, job.search_calls)
    summary = f"结束：{status}｜完成 {len(job.results)}/{len(job.rows)}｜失败 {len(failed)}"
    await anyio.to_thread.run_sync(_log, job, summary)
    values = {
        **_progress(job),
        "status": status,
        "finished_at": utcnow(),
        "error_message": message,
        "inference_cost": inference,
        "search_cost": search,
        "cancel_requested": False,
    }
    async with SessionLocal() as session:
        await repo.update_fields(session, job.run.id, values)
        await session.commit()


async def _fail(run_id: str, message: str) -> None:
    async with SessionLocal() as session:
        await repo.update_fields(
            session, run_id, {"status": RUN_FAILED, "error_message": message[:ERROR_MAX], "finished_at": utcnow()}
        )
        await session.commit()


async def _run_job(job: Job) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        await repo.update_fields(session, job.run.id, {"total_count": len(job.rows), **_progress(job)})
        await session.commit()
    await anyio.to_thread.run_sync(start_raw, job.path("raw"))
    await anyio.to_thread.run_sync(
        _log, job, f"开始：模型={job.model.name}｜{len(job.rows)} 条｜并发={settings.batch_concurrency}"
    )
    limits = httpx.Limits(max_connections=settings.batch_concurrency)
    watcher = asyncio.create_task(_watch(job))
    try:
        async with httpx.AsyncClient(limits=limits) as client:
            await asyncio.gather(*(_consume(job, client) for _ in range(settings.batch_concurrency)))
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher


async def execute(run_id: str) -> None:
    """任何异常都落到任务状态上，worker 不退出。进程被停止（取消）时把已跑部分收尾成「中断」。"""

    async with SessionLocal() as session:
        run = await repo.get(session, run_id)
    if run is None:
        return
    try:
        job = await _load(run)
    except Exception as exc:  # noqa: BLE001  读 Excel 失败要落到任务上让用户看到原因
        await _fail(run_id, str(exc))
        return
    try:
        await _run_job(job)
    except asyncio.CancelledError:
        await asyncio.shield(_finish(job, RUN_INTERRUPTED, "执行进程停止（服务重启），已跑完的部分已生成结果"))
        raise
    except Exception as exc:
        # 单个任务异常不能拖垮 worker，落到任务状态上让用户看到原因。
        logger.exception("batch_run_failed run=%s", run_id)
        await _finish(job, RUN_FAILED, f"执行失败：{exc}"[:ERROR_MAX])
        return
    stopped_early = job.stop.is_set() and len(job.results) < len(job.rows)
    await _finish(job, RUN_CANCELLED if stopped_early else RUN_DONE)
