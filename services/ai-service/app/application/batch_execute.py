"""执行一个批量任务，由 worker 调用。

N 个协程从同一个队列取行并发提问；每完成一行立即追加到原始返回 CSV，进程中途被杀也保留已跑结果。
另一个协程定时写进度和心跳，并检查停止标志：置位后不再取新行，等在途请求返回后收尾。

每行自动补救：限流、超时这类可重试的错误退避后重发；回答解析不出输出字段时重问一次，仍不行记为「格式不对」。
任务目录里已有原始返回时是续跑：已成功的行直接沿用，只问失败和没跑到的行，结果合并回同一个任务。
费用每行完成时按当时的单价累加：分时计价的模型跨高峰、空闲时段跑，也按各行实际时段算。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import anyio
import httpx
from platform_common.clock import utcnow
from platform_common.excel import run_excel_parse

from app.application import model_configs
from app.application.asking import llm_request
from app.application.batch_output import (
    FORMAT_ERROR_PREFIX,
    RowResult,
    append_log,
    append_raw,
    build_result,
    read_raw,
    start_raw,
    write_failed,
)
from app.application.sheets import read_run_input
from app.core import storage
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.llm import stream_responses
from app.domain.llm_models import LlmModel, build_body, calc_costs, with_service_tier
from app.domain.models import RUN_CANCELLED, RUN_DONE, RUN_FAILED, RUN_INTERRUPTED, BatchRun
from app.domain.templating import build_myid, fill_template, parse_fields, split_fields
from app.repositories import batch_runs as repo

logger = logging.getLogger("ai.batch")
PROGRESS_SECONDS = 2.0
ERROR_MAX = 2000
# 可重试错误的退避秒数，次数即重试次数；实际等待再乘 1~1.5 的随机系数，避免 20 路并发同时撞回去。
RETRY_DELAYS = (3.0, 10.0)
FORMAT_RETRIES = 1


@dataclass
class Job:
    run: BatchRun
    model: LlmModel
    headers: list[str]
    rows: list[dict[str, str]]
    # 还没问的行号。提示词轮到哪行才拼哪行：10 万行乘上码表全文一次拼好要几个 G，worker 会被 OOM 杀掉。
    pending: deque[str]
    code_text: str = ""
    by_id: dict[str, dict[str, str]] = field(default_factory=dict)
    fields: list[str] = field(default_factory=list)
    results: dict[str, RowResult] = field(default_factory=dict)
    # 续跑前失败的结果：重问后被新结果替换；中途停止没轮到的行仍用它出现在结果里。
    previous: dict[str, RowResult] = field(default_factory=dict)
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    # 不是用户点停止、而是任务自己停的原因（如到了费用上限），写进任务的错误信息。
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    search_calls: int = 0
    inference_cost: Decimal = Decimal(0)
    search_cost: Decimal = Decimal(0)

    def path(self, kind: str) -> Any:
        return storage.run_file(self.run.id, kind)

    def merged(self) -> dict[str, RowResult]:
        return {**self.previous, **self.results}


async def call_model_once(model: LlmModel, prompt: str, thinking: bool, client: httpx.AsyncClient) -> RowResult:
    """消费整条流，只要最终文本、用量、错误和联网次数。联网次数优先用 usage 里的权威值，没有就数进度事件。"""

    started = time.monotonic()
    parts: list[str] = []
    usage: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    search_events = 0
    async for event in stream_responses(llm_request(model, build_body(model, prompt, thinking=thinking)), client):
        if "text" in event:
            parts.append(event["text"])
        elif "usage" in event:
            usage = event["usage"]
        elif "error" in event:
            errors.append(event)
        elif event.get("tool_event", {}).get("stage") == "web_search_in_progress":
            search_events += 1
    return RowResult(
        myid="",
        prompt=prompt,
        text="".join(parts),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        search_calls=usage.get("web_search", search_events),
        error=errors[-1]["error"] if errors else "",
        elapsed=round(time.monotonic() - started, 2),
        retryable=bool(errors and errors[-1].get("retryable")),
    )


def needs_retry(result: RowResult, fields: list[str]) -> bool:
    return bool(result.error) or (bool(fields) and parse_fields(result.text, fields) is None)


async def ask_row(
    model: LlmModel, prompt: str, thinking: bool, fields: list[str], client: httpx.AsyncClient
) -> RowResult:
    """问一行，按规则自动补救。几次尝试的 token 和联网次数都算进这一行：钱已经花出去了。"""

    delays = list(RETRY_DELAYS)
    format_retries = FORMAT_RETRIES
    spent = [0, 0, 0]
    attempts = 0
    while True:
        result = await call_model_once(model, prompt, thinking, client)
        attempts += 1
        spent = [spent[0] + result.input_tokens, spent[1] + result.output_tokens, spent[2] + result.search_calls]
        if result.error and result.retryable and delays:
            await asyncio.sleep(delays.pop(0) * random.uniform(1.0, 1.5))  # noqa: S311  退避抖动，不涉及安全
            continue
        if not result.error and needs_retry(result, fields):
            if format_retries:
                format_retries -= 1
                continue
            result.error = f"{FORMAT_ERROR_PREFIX}：回答里没有解析出输出字段（{'、'.join(fields)}）"
        break
    result.input_tokens, result.output_tokens, result.search_calls = spent
    result.attempts = attempts
    return result


def _log(job: Job, message: str) -> None:
    stamp = utcnow().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    append_log(job.path("log"), f"{stamp} {message}")


async def _record(job: Job, result: RowResult) -> None:
    job.results[result.myid] = result
    job.input_tokens += result.input_tokens
    job.output_tokens += result.output_tokens
    job.search_calls += result.search_calls
    inference, search = calc_costs(job.model, result.input_tokens, result.output_tokens, result.search_calls, utcnow())
    job.inference_cost += inference
    job.search_cost += search
    limit = job.run.cost_limit
    if limit is not None and job.inference_cost + job.search_cost >= limit and not job.stop.is_set():
        # 在途的几行仍会返回并计费，所以实际花费会略超上限，超出部分不超过并发数那几行。
        job.stop_reason = f"达到本批费用上限 {limit:.2f} 元，已停止提交新的提问"
        job.stop.set()
    head = f"[{len(job.results)}/{len(job.rows)}] {result.myid}"
    tries = f" 尝试={result.attempts}次" if result.attempts > 1 else ""
    if result.error:
        line = f"{head} {result.failure_kind} 耗时={result.elapsed}s{tries} 错误={result.error}"
    else:
        line = f"{head} 成功 耗时={result.elapsed}s{tries}"
    await anyio.to_thread.run_sync(append_raw, job.path("raw"), result.raw_row(job.model.name))
    await anyio.to_thread.run_sync(_log, job, line)
    # 提问原文已经落在原始返回 CSV 里；成功的行不再留着它（失败清单要写失败行的提问，失败的留着）。
    if not result.error:
        result.prompt = ""


async def _consume(job: Job, client: httpx.AsyncClient) -> None:
    while job.pending and not job.stop.is_set():
        myid = job.pending.popleft()
        prompt = fill_template(job.run.prompt_content, job.by_id[myid], job.code_text)
        result = await ask_row(job.model, prompt, job.run.thinking, job.fields, client)
        result.myid = myid
        await _record(job, result)


def _progress(job: Job, *, final: bool = False) -> dict[str, Any]:
    """运行中「已处理」只数本轮已有结果，进度条才会往前走；失败数始终按合并后的结果算。"""

    merged = job.merged()
    failed = [item for item in merged.values() if item.error]
    return {
        "done_count": len(merged if final else job.results),
        "failed_count": len(failed),
        "format_failed_count": sum(1 for item in failed if item.format_error),
        "input_tokens": job.input_tokens,
        "output_tokens": job.output_tokens,
        "search_calls": job.search_calls,
        "inference_cost": job.inference_cost,
        "search_cost": job.search_cost,
        "heartbeat_at": utcnow(),
    }


async def _watch(job: Job) -> None:
    """写进度和心跳；发现停止标志就让取行协程停手。"""

    while True:
        await asyncio.sleep(PROGRESS_SECONDS)
        # 库连接抖一下不能让它死掉：它一死心跳就停，任务被误判中断、停止按钮失效、跑完还被记成失败。
        try:
            async with SessionLocal() as session:
                await repo.update_fields(session, job.run.id, _progress(job))
                if await repo.cancel_flag(session, job.run.id):
                    job.stop.set()
                await session.commit()
        except Exception:
            logger.exception("batch_run_watch_failed run=%s", job.run.id)


async def _load(run: BatchRun) -> Job:
    # 停用的模型也照跑：任务是停用前排进来的。
    async with SessionLocal() as session:
        config = await model_configs.find(session, run.model_id)
        # 解析 Excel、读回原始返回、拼全部提示词可能超过心跳超时：先报一次平安，大任务别一开始就被当成中断。
        await repo.update_fields(session, run.id, {"heartbeat_at": utcnow()})
        await session.commit()
    if config is None:
        raise RuntimeError(f"未知模型：{run.model_id}")
    model = with_service_tier(model_configs.to_model(config), run.service_tier)
    headers, rows = await run_excel_parse(read_run_input, storage.run_dir(run.id))
    if run.row_limit > 0:
        rows = rows[: run.row_limit]
    if not rows:
        raise RuntimeError("Excel 没有数据行")
    code = storage.run_dir(run.id) / storage.PROMPT_FILES["code"]
    code_text = await anyio.Path(code).read_text(encoding="utf-8") if await anyio.Path(code).is_file() else ""
    for index, row in enumerate(rows):
        row["myid"] = build_myid(index)
    fields = split_fields(run.output_fields)
    existing = await anyio.to_thread.run_sync(read_raw, storage.run_file(run.id, "raw"))
    ids = {row["myid"] for row in rows}
    succeeded = {key: item for key, item in existing.items() if key in ids and not needs_retry(item, fields)}
    previous = {key: item for key, item in existing.items() if key in ids and key not in succeeded}
    for item in succeeded.values():
        item.prompt = ""
    return Job(
        run=run,
        model=model,
        headers=headers,
        rows=rows,
        pending=deque(row["myid"] for row in rows if row["myid"] not in succeeded),
        code_text=code_text,
        by_id={row["myid"]: row for row in rows},
        fields=fields,
        results=succeeded,
        previous=previous,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        search_calls=run.search_calls,
        inference_cost=run.inference_cost,
        search_cost=run.search_cost,
    )


async def _finish(job: Job, status: str, message: str = "") -> None:
    merged = job.merged()
    if merged:
        await anyio.to_thread.run_sync(
            build_result, job.path("result"), job.headers, job.rows, merged, job.fields, job.model.name
        )
    failed = [item for item in merged.values() if item.error]
    failed_file = job.path("failed")
    if failed:
        await anyio.to_thread.run_sync(write_failed, failed_file, failed)
    elif await anyio.Path(failed_file).is_file():
        await anyio.Path(failed_file).unlink()
    formats = sum(1 for item in failed if item.format_error)
    summary = f"结束：{status}｜完成 {len(merged)}/{len(job.rows)}｜失败 {len(failed)}（格式不对 {formats}）"
    await anyio.to_thread.run_sync(_log, job, summary)
    values = {
        **_progress(job, final=True),
        "status": status,
        "finished_at": utcnow(),
        "error_message": message,
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
    scope = f"{len(job.rows)} 条"
    if job.results or job.previous:
        scope = f"续跑 {len(job.pending)} 条（共 {len(job.rows)} 条，已成功 {len(job.results)} 条）"
    await anyio.to_thread.run_sync(
        _log, job, f"开始：模型={job.model.name}｜{scope}｜并发={settings.batch_concurrency}"
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
    await _finish(job, RUN_CANCELLED if stopped_early else RUN_DONE, job.stop_reason if stopped_early else "")
