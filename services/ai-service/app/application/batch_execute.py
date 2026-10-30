"""执行一个批量任务，由 worker 调用。

N 个协程从同一个队列取行并发提问；每完成一行立即追加到原始返回 CSV，进程中途被杀也保留已跑结果。
另一个协程定时写进度和心跳，并检查停止标志：置位后不再取新行，等在途请求返回后收尾。

每行当场补救：限流、超时这类可重试的错误退避后重发。
批量任务和定时任务一次执行最多跑三轮：一轮跑完，隔一会儿只重问网络失败（超时、断连、限流、空返回）和
格式不对（解析不出输出字段）的行，哪一轮全部成功就提前结束，三轮后仍失败的留着失败原因。
样本试跑不分轮：格式不对当场再问一次，结果原样给人看，好知道提示词哪里要改。
任务目录里已有原始返回时是续跑：已成功的行直接沿用，只问失败和没跑到的行，结果合并回同一个任务。
费用每行完成时按当时的单价累加：分时计价的模型跨高峰、空闲时段跑，也按各行实际时段算。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

import anyio
import httpx
from platform_common.clock import BEIJING, utcnow
from platform_common.excel import run_excel_parse

from app.application import model_configs
from app.application.batch_output import (
    RowResult,
    append_log,
    append_raw,
    build_result,
    read_raw,
    start_raw,
    write_failed,
)
from app.application.row_asking import FORMAT_RETRIES, ask_row, needs_retry, round_retry
from app.application.run_costs import Ledger, Spend, book
from app.application.run_heartbeat import beating
from app.application.sheets import read_run_input
from app.core import storage
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.llm_models import LlmModel, calc_costs, with_service_tier
from app.domain.models import (
    RUN_CANCELLED,
    RUN_DONE,
    RUN_FAILED,
    RUN_INTERRUPTED,
    RUN_SOURCE_SAMPLE,
    BatchRun,
)
from app.domain.templating import build_myid, fill_template, split_fields
from app.repositories import batch_runs as repo

logger = logging.getLogger("ai.batch")
PROGRESS_SECONDS = 2.0
ERROR_MAX = 2000
ROUNDS = 3
# 第 2、3 轮开始前各等多久：网络抖动、限流常持续几十秒到几分钟，紧接着重发大概率还是失败。
ROUND_WAITS = (60.0, 300.0)


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
    # 续跑前、上一轮失败的结果：重问后被新结果替换；中途停止没轮到的行仍用它出现在结果里。
    previous: dict[str, RowResult] = field(default_factory=dict)
    rounds: int = ROUNDS
    format_retries: int = 0
    round: int = 1
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    # 不是用户点停止、而是任务自己停的原因（如到了费用上限），写进任务的错误信息。
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    search_calls: int = 0
    inference_cost: Decimal = Decimal(0)
    search_cost: Decimal = Decimal(0)
    # 这次执行花的钱按天记账（见 run_costs）：重跑、跨零点的钱记到实际花钱那天。
    ledger: Ledger = field(default_factory=Ledger)
    # 几路并发答完的行排队写原始返回：结果记录里记的字节位置才准（详情预览按位置取行）。
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # 等下一轮的时候被停了：这时每行都有结果（上一轮的），只看行数会把它收尾成「完成」、不写停止说明。
    rounds_cut: bool = False

    def path(self, kind: str) -> Any:
        return storage.run_file(self.run.id, kind)

    def merged(self) -> dict[str, RowResult]:
        return {**self.previous, **self.results}

    def prompt_of(self, myid: str) -> str:
        """失败清单要写提问原文：写的时候现拼，不常驻内存（几万行失败乘上码表全文能占几个 G）。"""

        return fill_template(self.run.prompt_content, self.by_id[myid], self.code_text)


def _log(job: Job, message: str) -> None:
    # 容器里没设时区，astimezone() 得到的是 UTC，和页面上的北京时间差 8 小时。
    stamp = utcnow().astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
    append_log(job.path("log"), f"{stamp} {message}")


async def _save(job: Job, values: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        await repo.update_fields(session, job.run.id, values)
        await session.commit()


async def _record(job: Job, result: RowResult) -> None:
    job.results[result.myid] = result
    job.input_tokens += result.input_tokens
    job.output_tokens += result.output_tokens
    job.search_calls += result.search_calls
    now = utcnow()
    inference, search = calc_costs(job.model, result.input_tokens, result.output_tokens, result.search_calls, now)
    job.inference_cost += inference
    job.search_cost += search
    job.ledger.add(now, Spend(result.input_tokens, result.output_tokens, result.search_calls, inference, search))
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
    async with job.write_lock:
        await anyio.to_thread.run_sync(append_raw, job.path("raw"), result.raw_row(job.model.name))
    await anyio.to_thread.run_sync(_log, job, line)
    # 提问原文已经落在原始返回 CSV 里，不再留着它；失败清单要的提问写文件时现拼（Job.prompt_of）。
    result.prompt = ""


async def _consume(job: Job, client: httpx.AsyncClient) -> None:
    while job.pending and not job.stop.is_set():
        myid = job.pending.popleft()
        prompt = fill_template(job.run.prompt_content, job.by_id[myid], job.code_text)
        result = await ask_row(
            job.model, prompt, job.run.thinking, job.fields, client, format_retries=job.format_retries
        )
        result.myid = myid
        await _record(job, result)


async def _next_round(job: Job) -> bool:
    """挑出上一轮网络失败、格式不对的行，等一会儿只重问它们。没有要重问的，或等的时候有人点了停止，返回 False。"""

    again = [
        row["myid"] for row in job.rows if (result := job.results.get(row["myid"])) is not None and round_retry(result)
    ]
    if not again:
        return False
    job.round += 1
    wait = ROUND_WAITS[min(job.round - 2, len(ROUND_WAITS) - 1)]
    starts = utcnow() + timedelta(seconds=wait)
    await _save(job, {"retry_round": job.round, "round_rows": len(again), "round_starts_at": starts})
    message = f"第 {job.round} 轮：上一轮 {len(again)} 条网络失败或格式不对，{wait:.0f} 秒后重问"
    await anyio.to_thread.run_sync(_log, job, message)
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(job.stop.wait(), timeout=wait)
    if job.stop.is_set():
        job.rounds_cut = True
        return False
    for myid in again:
        job.previous[myid] = job.results.pop(myid)
    job.pending.extend(again)
    return True


def _progress(job: Job, *, final: bool = False) -> dict[str, Any]:
    """运行中「已处理」只数本轮已有结果，进度条才会往前走；失败数始终按合并后的结果算。"""

    merged = job.merged()
    failed = [item for item in merged.values() if item.error]
    answered = sum(1 for item in merged.values() if not item.error)
    return {
        "open_count": len(job.rows) - answered,
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
        taken, booked = job.ledger.take(), False
        try:
            async with SessionLocal() as session:
                alive = await repo.update_if_running(session, job.run.id, _progress(job))
                cancelled = await repo.cancel_flag(session, job.run.id)
                await book(session, job.run.id, taken)
                await session.commit()
                # 提交了就算记上：在退出会话（关连接）时被取消的话，放回去会让收尾再记一遍，同一笔钱记两次。
                booked = True
        except Exception:
            logger.exception("batch_run_watch_failed run=%s", job.run.id)
            continue
        finally:
            # 没记上（写库失败，或者收尾时被取消在半路）就放回去，由下一次或收尾时再记。
            if not booked:
                job.ledger.restore(taken)
        if not alive and not job.stop.is_set():
            # 心跳断过一阵、任务已被纠正成「中断」：页面上停止按钮已经没了，这里不停就会一直花钱。
            logger.warning("batch_run_no_longer_running run=%s", job.run.id)
            job.stop_reason = "任务已被判定中断（有一阵子没写上心跳），不再提交新的提问"
            job.stop.set()
        if cancelled:
            job.stop.set()


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
    sample = run.source == RUN_SOURCE_SAMPLE
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
        rounds=1 if sample else ROUNDS,
        format_retries=FORMAT_RETRIES if sample else 0,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        search_calls=run.search_calls,
        inference_cost=run.inference_cost,
        search_cost=run.search_cost,
    )


async def _finish(job: Job, status: str, message: str = "") -> None:
    merged = job.merged()
    failed = [item for item in merged.values() if item.error]
    failed_file = job.path("failed")
    async with beating(job.run.id):
        if merged:
            await anyio.to_thread.run_sync(
                build_result, job.path("result"), job.headers, job.rows, merged, job.fields, job.model.name
            )
        if failed:
            await anyio.to_thread.run_sync(write_failed, failed_file, failed, job.prompt_of)
        elif await anyio.Path(failed_file).is_file():
            await anyio.Path(failed_file).unlink()
    formats = sum(1 for item in failed if item.format_error)
    summary = f"结束：{status}｜完成 {len(merged)}/{len(job.rows)}｜失败 {len(failed)}（格式不对 {formats}）"
    if job.round > 1:
        summary += f"｜共跑 {job.round} 轮"
    await anyio.to_thread.run_sync(_log, job, summary)
    values = {
        **_progress(job, final=True),
        "status": status,
        "finished_at": utcnow(),
        "error_message": message,
        "cancel_requested": False,
        "round_starts_at": None,
    }
    # 钱已经花出去了：任务被纠正成「中断」、这次的进度写不上，流水照样记。
    async with SessionLocal() as session:
        written = await repo.update_if_running(session, job.run.id, values, also=(RUN_INTERRUPTED,))
        await book(session, job.run.id, job.ledger.take())
        await session.commit()
    if not written:
        # 被纠正成「中断」后又被人点了重跑：排队中的任务下次会沿用这次已跑好的行，不拿这次的结果盖掉排队状态。
        logger.warning("batch_run_finish_skipped run=%s status=%s", job.run.id, status)


async def _fail(run_id: str, message: str) -> None:
    async with SessionLocal() as session:
        await repo.update_fields(
            session, run_id, {"status": RUN_FAILED, "error_message": message[:ERROR_MAX], "finished_at": utcnow()}
        )
        await session.commit()


async def _run_job(job: Job) -> None:
    settings = get_settings()
    first = {"total_count": len(job.rows), "retry_round": 1, "round_rows": len(job.pending), "round_starts_at": None}
    await _save(job, {**first, **_progress(job)})
    await anyio.to_thread.run_sync(start_raw, job.path("raw"))
    scope = f"{len(job.rows)} 条"
    if job.results or job.previous:
        scope = f"续跑 {len(job.pending)} 条（共 {len(job.rows)} 条，已成功 {len(job.results)} 条）"
    await anyio.to_thread.run_sync(
        _log, job, f"开始：模型={job.model.name}｜{scope}｜并发={settings.batch_concurrency}"
    )
    limits = httpx.Limits(max_connections=settings.batch_concurrency)
    # 心跳要盖住轮与轮之间的等待：等 5 分钟不写心跳，就会被当成执行进程不在了、纠正成「中断」。
    watcher = asyncio.create_task(_watch(job))
    try:
        async with httpx.AsyncClient(limits=limits) as client:
            while True:
                await asyncio.gather(*(_consume(job, client) for _ in range(settings.batch_concurrency)))
                # 停止（含到了费用上限）就不再开下一轮；全部成功或跑满三轮也结束。
                if job.stop.is_set() or job.round >= job.rounds or not await _next_round(job):
                    break
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
        async with beating(run_id):
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
    stopped_early = job.stop.is_set() and (len(job.results) < len(job.rows) or job.rounds_cut)
    await _finish(job, RUN_CANCELLED if stopped_early else RUN_DONE, job.stop_reason if stopped_early else "")
