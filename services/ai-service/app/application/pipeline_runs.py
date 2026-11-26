"""流水线任务：政策服务定时打标时，用模板的上线版本跑一批数据，再把解析后的结果取回去写业务表。

定时任务没人盯着，只跑上线版本（页面上的批量任务还能选跑草稿）；和批量任务共用同一套执行（worker、三轮重跑、计费、历史），
区别只在：
- 输入不是上传的 Excel，而是调用方传来的行，原样存成 rows.json（政策正文可能十几万字，Excel 单元格放不下）；
- 按低优档跑，并带费用上限，到上限自动停；
- 调用方那一批中断、失败后重读同一批数据时，可以带上上一批的任务ID：已经答好、内容没变的行直接沿用，不再花钱重问。
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import batch_runs, prompts, releases
from app.application.asking import RELEASE_MODEL_DISABLED, resolve_model
from app.application.audit_emit import enqueue_event
from app.application.batch_output import append_log, copy_answers, read_raw
from app.application.batch_runs import require as require_run
from app.application.batch_runs import to_dict as run_to_dict
from app.application.sheets import has_run_input, read_run_input
from app.core import storage
from app.domain.categories import DEFAULT_CATEGORY, FULL_ACCESS
from app.domain.code_tables import code_table_name
from app.domain.models import (
    ACTIVE_STATUSES,
    RUN_CANCELLED,
    RUN_QUEUED,
    RUN_SOURCE_PIPELINE,
    BatchRun,
    TemplateRelease,
    new_id,
)
from app.domain.templating import build_myid, parse_fields, split_fields, template_variables
from app.repositories import batch_runs as run_repo
from app.repositories import releases as release_repo

logger = logging.getLogger("ai.pipeline")
# 每行带上它，结果按它对回调用方的数据，不依赖行号。
SOURCE_ID = "源ID"
ROWS_MAX = 20_000
PIPELINE_TIER = "flex"
TOMBSTONE_TITLE = "（调用方已放弃的定时任务）"
TOMBSTONE_NOTE = "调用方在任务建好之前已经放弃（超时或中断）：这一行占住任务ID，迟到的建任务请求不再执行"
_ZERO_COUNTS = (
    "total_count",
    "done_count",
    "failed_count",
    "format_failed_count",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
)


def _invalid(message: str) -> ApiError:
    return ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)


def _checked_rows(rows: object) -> tuple[list[str], list[dict[str, str]]]:
    if not isinstance(rows, list) or not rows:
        raise _invalid("没有要提问的数据")
    if len(rows) > ROWS_MAX:
        raise _invalid(f"一次最多 {ROWS_MAX} 行")
    headers: list[str] = []
    cleaned: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get(SOURCE_ID) or "").strip():
            raise _invalid(f"每行都要有「{SOURCE_ID}」")
        item = {str(key): "" if value is None else str(value) for key, value in row.items()}
        headers.extend(key for key in item if key not in headers)
        cleaned.append(item)
    return headers, cleaned


def _cost_limit(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        limit = Decimal(str(value))
    except InvalidOperation as exc:
        raise _invalid("费用上限不是有效金额") from exc
    if limit <= 0:
        raise _invalid("费用上限必须大于 0")
    return limit


async def _release(session: AsyncSession, prompt_id: str) -> TemplateRelease:
    # 读上线版本时锁住模板行：读的同时有人下线、重新上线，拿到的版本和模板对不上。读完调用方马上提交放锁。
    template = await prompts.require(session, prompt_id, lock=True)
    return await releases.current(session, template, "定时任务")


def _write_snapshot(run_id: str, headers: list[str], rows: list[dict[str, str]], code: str | None) -> None:
    target = storage.run_dir(run_id)
    target.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"headers": headers, "rows": rows}, ensure_ascii=False).encode("utf-8")
    storage.write_atomic(target / storage.ROWS_FILE, payload)
    if code is not None:
        storage.write_atomic(target / storage.PROMPT_FILES["code"], code.encode("utf-8"))


async def _reusable(session: AsyncSession, run_id: str, release: TemplateRelease, model_id: str) -> BatchRun | None:
    """上一批能不能沿用：同一个模板的同一版上线版本、同一个模型，已经结束（还在跑的答案还没写完）。"""

    if not storage.ID_PATTERN.fullmatch(run_id):
        return None
    previous = await run_repo.get(session, run_id)
    if previous is None or previous.source != RUN_SOURCE_PIPELINE or previous.status in ACTIVE_STATUSES:
        return None
    same = (previous.prompt_id, previous.release_no, previous.model_id, previous.output_fields) == (
        release.prompt_id,
        release.release_no,
        model_id,
        release.output_fields,
    )
    return previous if same else None


def _row_key(row: dict[str, str]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True)


def _reuse_answers(previous: BatchRun, run_id: str, rows: list[dict[str, str]], code: str | None) -> int:
    """把上一批里答好、而且这一批里内容一模一样的行抄过来。码表（系统码表是实时取的）也得一样，提问才一样。"""

    source = storage.run_dir(previous.id)
    code_file = source / storage.PROMPT_FILES["code"]
    previous_code = code_file.read_text(encoding="utf-8") if code_file.is_file() else None
    if previous_code != code or not has_run_input(source):
        return 0
    wanted: dict[str, list[str]] = {}
    for index, row in enumerate(rows):
        wanted.setdefault(_row_key(row), []).append(build_myid(index))
    _, old_rows = read_run_input(source)
    mapping = {build_myid(index): wanted[key] for index, row in enumerate(old_rows) if (key := _row_key(row)) in wanted}
    if not mapping:
        return 0
    fields = split_fields(previous.output_fields)
    copied = copy_answers(storage.run_file(previous.id, "raw"), storage.run_file(run_id, "raw"), mapping, fields)
    if copied:
        line = f"{format_beijing(utcnow())} 沿用上一批（任务 {previous.id}）已答好的 {copied} 条，不再重问"
        append_log(storage.run_file(run_id, "log"), line)
    return copied


async def _idempotent_replay(session: AsyncSession, client_run_id: str) -> dict[str, Any] | None:
    if not client_run_id:
        return None
    if not storage.ID_PATTERN.fullmatch(client_run_id):
        raise _invalid("client_run_id 格式无效")
    existing = await run_repo.get(session, client_run_id, deleted=True)
    if existing is not None and existing.source == RUN_SOURCE_PIPELINE:
        return {**run_to_dict(existing), "reused": 0}
    return None


async def _cleanup_run_dir(run_id: str) -> None:
    try:
        await anyio.to_thread.run_sync(storage.remove_tree, storage.run_dir(run_id))
    except OSError:
        logger.warning("pipeline_run_cleanup_failed run=%s", run_id, exc_info=True)


async def create(session: AsyncSession, caller: Actor, values: dict[str, Any]) -> dict[str, Any]:
    client_run_id = str(values.get("client_run_id") or "").strip()
    if replay := await _idempotent_replay(session, client_run_id):
        return replay
    headers, rows = _checked_rows(values.get("rows"))
    cost_limit = _cost_limit(values.get("cost_limit"))
    release = await _release(session, str(values.get("prompt_id") or ""))
    model = await resolve_model(session, release.model_id, frozen=RELEASE_MODEL_DISABLED)
    previous = await _reusable(session, str(values.get("reuse_run_id") or ""), release, model.id)
    # 库里要读的读完就提交，放掉模板行锁和读事务：下面取系统码表、写几十 MB 的快照、读上一批的原始返回
    # 可能要几分钟，事务开着会撞接口进程的空闲事务超时被断开（整批失败、目录留在盘上），锁也会挡住上线、下线。
    await session.commit()
    code = await releases.release_code(release)
    prompts.require_code(release.content, code)
    run_id = client_run_id or new_id()
    await anyio.to_thread.run_sync(_write_snapshot, run_id, headers, rows, code)
    reused = 0
    if previous is not None:
        reused = await anyio.to_thread.run_sync(_reuse_answers, previous, run_id, rows, code)
        logger.info("pipeline_run_reused run=%s previous=%s rows=%s", run_id, previous.id, reused)
    run = BatchRun(
        id=run_id,
        prompt_id=release.prompt_id,
        prompt_title=release.title,
        prompt_category=release.category,
        prompt_content=release.content,
        output_fields=release.output_fields,
        model_id=model.id,
        model_name=model.name,
        thinking=False,
        row_limit=0,
        status=RUN_QUEUED,
        **dict.fromkeys(_ZERO_COUNTS, 0),
        search_calls=0,
        inference_cost=Decimal(0),
        search_cost=Decimal(0),
        cancel_requested=False,
        error_message="",
        created_at=utcnow(),
        created_by_id=caller.id,
        created_by_name=caller.name,
        source=RUN_SOURCE_PIPELINE,
        release_no=release.release_no,
        service_tier=PIPELINE_TIER,
        cost_limit=cost_limit,
    )
    run_repo.add(session, run)
    try:
        await session.flush()
    except IntegrityError:
        if not client_run_id:
            await _cleanup_run_dir(run_id)
            raise
        await session.rollback()
        existing = await run_repo.get(session, client_run_id, deleted=True)
        if existing is not None and existing.source == RUN_SOURCE_PIPELINE:
            # 若抢输给已取消占位（tombstone，prompt_id 为空），不会再有执行进程使用该目录，直接清理。
            if not existing.prompt_id:
                await _cleanup_run_dir(run_id)
            return {**run_to_dict(existing), "reused": 0}
        await _cleanup_run_dir(run_id)
        raise
    changes: dict[str, Any] = {"prompt_id": release.prompt_id, "release_no": release.release_no, "rows": len(rows)}
    if reused:
        changes["reused_rows"] = reused
    await enqueue_event(
        session,
        event_type="ai.batch_run.started",
        actor=caller,
        category=run.prompt_category,
        target_id=run.id,
        changes=changes,
    )
    return {**run_to_dict(run), "reused": reused}


async def _tombstone(session: AsyncSession, run_id: str, caller: Actor) -> BatchRun | None:
    """调用方停止一个还不存在的任务：插一行已取消的占位，抢不过（建任务刚好先插进去）返回 None。

    政策服务建任务超时就立刻叫停，可这边的建任务请求可能还在写快照、行还没插进去，叫停只得到 404；
    不占位的话迟到的建任务照样插入、worker 照样跑、照样花钱，政策服务却已经不管它，也不计入当日费用。
    占位后迟到的插入撞主键，按幂等重放拿到这条已取消的任务，不会执行。
    """

    if not storage.ID_PATTERN.fullmatch(run_id):
        raise NotFoundError("任务不存在或已删除")
    now = utcnow()
    tombstone = BatchRun(
        id=run_id,
        prompt_id="",
        prompt_title=TOMBSTONE_TITLE,
        prompt_category=DEFAULT_CATEGORY,
        retry_round=1,
        round_rows=0,
        model_id="",
        model_name="",
        thinking=False,
        row_limit=0,
        status=RUN_CANCELLED,
        **dict.fromkeys(_ZERO_COUNTS, 0),
        search_calls=0,
        inference_cost=Decimal(0),
        search_cost=Decimal(0),
        cancel_requested=False,
        error_message=TOMBSTONE_NOTE,
        created_at=now,
        finished_at=now,
        created_by_id=caller.id,
        created_by_name=caller.name,
        source=RUN_SOURCE_PIPELINE,
        service_tier=PIPELINE_TIER,
    )
    try:
        async with session.begin_nested():
            run_repo.add(session, tombstone)
    except IntegrityError:
        return None
    logger.warning("pipeline_run_tombstone run=%s caller=%s", run_id, caller.id)
    return tombstone


async def status(session: AsyncSession, run_id: str) -> dict[str, Any]:
    # worker 被强杀又没拉起时，没心跳的任务要先纠正成「中断」，政策服务才不会一直轮询到自己超时。
    # 只读查询绝不写 tombstone：建任务正在写快照时页面轮询查不到，应直接返回 404，只有 stop() 才能占位取消。
    await batch_runs.reconcile_stale(session)
    return run_to_dict(await require_run(session, run_id))


def _parse_results(run_id: str, output_fields: str) -> list[dict[str, Any]]:
    _, rows = read_run_input(storage.run_dir(run_id))
    raw = read_raw(storage.run_file(run_id, "raw"))
    fields = split_fields(output_fields)
    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        answer = raw.get(build_myid(index))
        if answer is None:
            results.append({"source_id": row.get(SOURCE_ID, ""), "items": [], "error": "未执行（任务停止或中断）"})
            continue
        items = [] if answer.error else parse_fields(answer.text, fields) or []
        results.append({"source_id": row.get(SOURCE_ID, ""), "items": items, "error": answer.error})
    return results


async def results(session: AsyncSession, run_id: str) -> dict[str, Any]:
    """逐行结果：解析出的字段（一行可能展开成多条）或失败原因。任务结束后才能取，运行中结果还不全。"""

    run = await require_run(session, run_id)
    if run.status in ACTIVE_STATUSES:
        raise ApiError("任务还在运行，结束后再取结果", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    if not has_run_input(storage.run_dir(run.id)):
        raise NotFoundError("任务的输入快照不存在")
    items = await anyio.to_thread.run_sync(_parse_results, run.id, run.output_fields)
    return {"run": run_to_dict(run), "items": items}


async def stop(session: AsyncSession, caller: Actor, run_id: str) -> dict[str, Any]:
    """调用方超时或被中断时停掉自己发起的任务，别让它在后台继续花钱。

    任务还不存在（建任务的请求还在路上）就先占位成已取消，见 _tombstone。
    """

    if await run_repo.get(session, run_id, deleted=True) is None and (
        tombstone := await _tombstone(session, run_id, caller)
    ):
        return run_to_dict(tombstone)
    return await batch_runs.stop_run(session, caller, FULL_ACCESS, run_id)


async def online_templates(session: AsyncSession, category: str) -> list[dict[str, Any]]:
    """可以给定时任务用的模板：已上线的，按类型筛。"""

    items = []
    for template in await prompts.online(session, category):
        release = (await release_repo.by_ids(session, [template.release_id or ""])).get(template.release_id or "")
        if release is None:
            continue
        items.append(
            {
                "prompt_id": template.id,
                "title": release.title,
                "release_no": release.release_no,
                "released_at": format_beijing(release.released_at),
                "model_id": release.model_id,
                "output_fields": split_fields(release.output_fields),
                # 政策服务按它核对模板能不能放进某个打标任务（用了哪些列、码表是不是系统的）。
                "variables": template_variables(release.content),
                "system_code": bool(release.code_table),
                "code": code_table_name(release.code_table) if release.code_table else release.code_name,
            }
        )
    return items
