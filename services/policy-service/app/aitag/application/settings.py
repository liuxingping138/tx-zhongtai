"""政策 AI 打标三个任务的设置、今日费用和进度（任务调度页用）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, DependencyUnavailableError, ErrorCode, NotFoundError, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.application.tagging import day_start, today
from app.aitag.domain.contract import check_template
from app.aitag.domain.models import PolicyAiRun, PolicyAiTask
from app.aitag.domain.tasks import TASKS, job_code
from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.common.audit_emit import enqueue_event

BATCH_SIZE_RANGE = (1, 20_000)
# 0 = 全文照传；要截就至少留 500 字。
CONTENT_RANGE = (500, 200_000)


def _task_out(task: PolicyAiTask) -> dict[str, Any]:
    return {
        "code": task.code,
        "job_code": job_code(task.code),
        "name": TASKS[task.code],
        "prompt_id": task.prompt_id,
        "batch_size": task.batch_size,
        "content_max_chars": task.content_max_chars,
        "daily_cost_limit": str(task.daily_cost_limit),
        "cursor_date": task.cursor_date.isoformat() if task.cursor_date else "",
        "cursor_content_id": task.cursor_content_id,
        "provinces": list(task.provinces or []),
        "version": task.version,
        "updated_at": format_beijing(task.updated_at),
        "updated_by_name": task.updated_by_name,
    }


async def _enrich_pending() -> int:
    """补描述的待办在码表服务里；取不到就当 0，不影响任务调度页。"""

    try:
        found = await internal_clients.codebook("GET", "/internal/v1/scenarios/enrich-count")
    except (ApiError, DependencyUnavailableError):
        return 0
    return int(found.get("pending") or 0)


async def list_tasks(session: AsyncSession) -> dict[str, Any]:
    """各任务的设置、今天和本月已花、正在跑的那一批进度。任务调度页每几秒刷新一次，这里不取模板列表。"""

    rows = await repo.tasks(session)
    running = await repo.running_runs(session)
    pending = {**await repo.pending_counts(session), "enrich": await _enrich_pending()}
    first_of_month = today().replace(day=1)
    items = []
    for code in TASKS:
        task = rows.get(code)
        if task is None:
            continue
        items.append(
            {
                **_task_out(task),
                "spent_today": str(await repo.spent_since(session, code, day_start(today()))),
                "spent_month": str(await repo.spent_since(session, code, day_start(first_of_month))),
                "current": await _current(running.get(code)),
                # 待办：类型判断是等着重新判断的，解读、市场机会是等着做的。
                "pending": pending.get(code, 0),
            }
        )
    return {"items": items}


def _with_checks(item: dict[str, Any]) -> dict[str, Any]:
    """每个上线模板放进三个任务各有没有问题（见 domain.contract），任务设置里据此提示、保存时据此拦下。"""

    variables, fields = list(item.get("variables") or []), list(item.get("output_fields") or [])
    system_code = bool(item.get("system_code"))
    return {**item, "checks": {code: check_template(code, variables, fields, system_code) for code in TASKS}}


async def _online_templates() -> list[dict[str, Any]]:
    items = await internal_clients.ai("GET", "/internal/v1/online-templates", params={"category": "policy"})
    return [_with_checks(item) for item in items]


async def templates() -> dict[str, Any]:
    """可选的上线模板（政策类）。ai-service 不可用时列表为空，原因显示在设置里，其余设置照样能改。"""

    try:
        return {"items": await _online_templates(), "error": ""}
    except Exception as exc:  # noqa: BLE001  模板列表取不到不影响看和改其余设置
        return {"items": [], "error": f"取上线模板失败：{exc}"}


async def _check_prompt(code: str, prompt_id: str) -> None:
    """换模板时核对：模板得是上线的政策类模板，放进这个任务没有必须改的问题。"""

    found = next((item for item in await _online_templates() if item["prompt_id"] == prompt_id), None)
    if found is None:
        raise ApiError(
            "选的模板不存在、不是政策类或已下线，请刷新后重选", code=ErrorCode.VALIDATION_ERROR, http_status=422
        )
    errors = found["checks"][code]["errors"]
    if errors:
        message = f"「{found['title']}」不能用于{TASKS[code]}：{'；'.join(errors)}"
        raise ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)


def _in_range(value: int, bounds: tuple[int, int], label: str) -> int:
    if not bounds[0] <= value <= bounds[1]:
        raise ApiError(f"{label}要在 {bounds[0]}～{bounds[1]} 之间", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return value


PROVINCE_MAX = 64  # 与基础标签「省份名称」列宽一致
PROVINCES_MAX = 50


def _provinces(values: Any) -> list[str]:
    """采集省份：去空白、去重、保持选的顺序。源库按 prov_name 原样比对，写法要和基础标签里的省份名称一致。"""

    picked = list(dict.fromkeys(str(item).strip() for item in values or [] if str(item).strip()))
    if len(picked) > PROVINCES_MAX:
        raise ApiError(f"采集省份最多选 {PROVINCES_MAX} 个", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if any(len(item) > PROVINCE_MAX for item in picked):
        raise ApiError(f"省份名称不能超过 {PROVINCE_MAX} 个字", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return picked


def _cursor_date(value: Any) -> date:
    cursor_date = date.fromisoformat(str(value))
    if cursor_date > today():
        raise ApiError("起始采集日期不能晚于今天", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return cursor_date


async def update_task(session: AsyncSession, actor: Actor, code: str, values: dict[str, Any]) -> dict[str, Any]:
    if code not in TASKS:
        raise NotFoundError("没有这个打标任务")
    task = await repo.task(session, code, lock=True)
    if int(values.get("version") or 0) != task.version:
        raise VersionConflictError("设置已被其他人修改，请刷新后重新保存")
    # 先全部校验再改，任何一项不合格都不留下改了一半的设置。
    limit = Decimal(str(values["daily_cost_limit"]))
    if limit < 0:
        raise ApiError("每日费用上限不能是负数", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    batch_size = _in_range(int(values["batch_size"]), BATCH_SIZE_RANGE, "每批条数")
    content_max = int(values["content_max_chars"])
    content_max = 0 if content_max == 0 else _in_range(content_max, CONTENT_RANGE, "正文截取字数")
    # 只有类型判断读源库，有读取进度。
    cursor_date = _cursor_date(values["cursor_date"]) if code == "type" and values.get("cursor_date") else None
    # 采集省份也只有类型判断用：其余任务按待办做，待办来自类型判断写进基础标签的政策。
    provinces = _provinces(values.get("provinces")) if code == "type" else []
    prompt_id = str(values.get("prompt_id") or "").strip()
    if prompt_id and prompt_id != task.prompt_id:
        await _check_prompt(code, prompt_id)
    before = _task_out(task)
    task.prompt_id = prompt_id
    task.batch_size, task.content_max_chars, task.daily_cost_limit = batch_size, content_max, limit
    # 改了起始日期就从那天的第一条重新读；没改就保持当前进度。
    if cursor_date is not None and cursor_date != task.cursor_date:
        task.cursor_date, task.cursor_content_id = cursor_date, ""
    # 改省份不动读取进度：已读过的日期里新加省份的政策，要把起始日期往前调才会补读（打过标的跳过，不重复花钱）。
    task.provinces = provinces
    task.version += 1
    task.updated_at, task.updated_by_name = utcnow(), actor.name
    after = _task_out(task)
    changed = {key: {"from": before[key], "to": after[key]} for key in after if before[key] != after[key]}
    await enqueue_event(
        session, event_type="policy.ai_tagging.config_updated", actor=actor, target_id=job_code(code), changes=changed
    )
    return after


# 进行到哪一步 -> 这一步在 ai-service 的任务ID列。
_STAGE_RUN = {
    "typing": "type_run_id",
    "interpreting": "interpret_run_id",
    "opportunity": "opportunity_run_id",
    "similar": "scenario_run_id",
    "describing": "enrich_run_id",
}
STAGE_NAMES = {
    "reading": "读取源政策",
    "typing": "模型判断中",
    "interpreting": "模型解读中",
    "opportunity": "模型回答中",
    "similar": "模型找相似场景中",
    "describing": "模型写描述中",
}


async def _current(run: PolicyAiRun | None) -> dict[str, Any] | None:
    """正在跑的那一批：在做什么、ai-service 答到第几条。取不到进度不影响页面。"""

    if run is None:
        return None
    current: dict[str, Any] = {
        "id": str(run.id),
        "stage": run.stage,
        "stage_name": STAGE_NAMES.get(run.stage, run.stage),
        "started_at": format_beijing(run.started_at),
        "cost": str(run.cost),
        "done": None,
        "total": None,
    }
    ai_run_id = getattr(run, _STAGE_RUN.get(run.stage, ""), "") or ""
    if ai_run_id:
        try:
            status = await internal_clients.ai("GET", f"/internal/v1/pipeline-runs/{ai_run_id}")
            current.update(done=status.get("done_count"), total=status.get("total_count"))
        except Exception:  # noqa: BLE001, S110  进度是锦上添花，ai-service 暂时不可用时页面照常显示其余信息
            pass
    return current
