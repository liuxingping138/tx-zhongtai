"""新增场景找相似：「新增场景审核」里待审的场景，连同码表里同一个一级行业下的全部场景交给模型，
让它挑出最像的已有场景、说是不是同一个场景。结果记在候选上，审核页的「系统建议」照它给。

一个场景只问一次（不按解读行问），输入是这个行业的场景清单，几千字；用上线模板、按每日费用上限跑，和其他打标任务一样。
"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.clock import utcnow
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.application.pipeline import ROBOT, Spend, ask, not_run, reused_note, update_run
from app.aitag.domain.models import PolicyAiTask
from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.common.audit_emit import enqueue_event
from app.core.database import SessionLocal
from app.policy.application import scenario_candidates
from app.policy.domain.candidates import (
    AI_FAILED,
    AI_ID,
    AI_NEW,
    AI_PATHS,
    AI_REASON_FIELD,
    AI_SIMILAR_FIELD,
    AI_VERDICT_FIELD,
    STATUS_PENDING,
    ScenarioCandidate,
    ai_path,
    ai_verdict,
)

CONTEXT_CHUNK = 500
NO_PATHS = "（码表里这个行业下还没有场景）"


async def _industry_paths(
    candidates: list[ScenarioCandidate], industries: dict[str, list[str]]
) -> dict[str, list[str]]:
    """每个场景所在一级行业下，码表里的全部场景路径（各级都列）。"""

    out: dict[str, list[str]] = {}
    for start in range(0, len(candidates), CONTEXT_CHUNK):
        items = [
            {
                "key": str(candidate.id),
                "path": [name for name in candidate.path() if name],
                "industry_l1": industries[str(candidate.id)],
                "with_paths": True,
            }
            for candidate in candidates[start : start + CONTEXT_CHUNK]
        ]
        found = await internal_clients.codebook("POST", "/internal/v1/scenarios/context", json={"items": items})
        out.update({str(item.get("key")): list(item.get("industry_paths") or []) for item in found})
    return out


async def prompt_rows(
    session: AsyncSession, candidates: list[ScenarioCandidate]
) -> tuple[list[dict[str, str]], dict[str, set[str]]]:
    """交给模板的行（列见 candidates.AI_COLUMNS），以及每个场景的参照清单（AI 说的场景要在里面才算对得上）。"""

    inputs = await scenario_candidates.ai_inputs(session, candidates)
    industries = {key: value["industries"] for key, value in inputs.items()}
    paths = await _industry_paths(candidates, industries)
    rows = []
    for candidate in candidates:
        key = str(candidate.id)
        rows.append(
            {
                AI_ID: key,
                "新增场景": " > ".join(name for name in candidate.path() if name),
                "新增级别": candidate.level_label,
                "一级行业": "、".join(industries[key]) or candidate.main_industry,
                "AI理由": "；".join(inputs[key]["reasons"]) or "（没有）",
                AI_PATHS: "\n".join(paths.get(key, [])) or NO_PATHS,
            }
        )
    return rows, {key: set(value) for key, value in paths.items()}


def _judge(candidate: ScenarioCandidate, result: dict[str, Any], known: set[str]) -> bool:
    """把模型的回答写到候选上，返回是否判断成功。AI 说的场景码表里对得上才记成建议合并的目标。"""

    items = result.get("items") or []
    first = items[0] if items else {}
    if result.get("error") or not first:
        candidate.ai_verdict = AI_FAILED
        candidate.ai_reason = str(result.get("error") or "AI 没有给出判断")[:500]
        candidate.ai_similar = candidate.ai_target = ""
        return False
    verdict = ai_verdict(str(first.get(AI_VERDICT_FIELD) or ""))
    similar = ai_path(str(first.get(AI_SIMILAR_FIELD) or ""))
    candidate.ai_verdict = verdict
    candidate.ai_similar = similar[:800]
    candidate.ai_target = similar[:800] if similar in known and verdict != AI_NEW else ""
    candidate.ai_reason = str(first.get(AI_REASON_FIELD) or "")[:2000]
    return True


async def _save(ids: list[uuid.UUID], results: list[dict[str, Any]], known: dict[str, set[str]]) -> dict[str, int]:
    done = failed = 0
    now = utcnow()
    async with SessionLocal() as session:
        # 按候选 ID 升序获取行锁，与其他场景处理接口锁序一致，防止死锁。
        for candidate_id, result in sorted(zip(ids, results, strict=True), key=lambda pair: pair[0]):
            if not_run(result):
                continue  # 费用到上限没轮到：下批再问
            candidate = await scenario_candidates.locked(session, candidate_id)
            if candidate is None or candidate.status != STATUS_PENDING:
                continue  # 问的时候有人已经做了决定
            if _judge(candidate, result, known.get(str(candidate_id), set())):
                done += 1
            else:
                failed += 1
            candidate.ai_checked_at = now
        await enqueue_event(
            session,
            event_type="policy.ai_tagging.scenario_judged",
            actor=ROBOT,
            extra={"judged": done, "failed": failed},
        )
        await session.commit()
    return {"done": done, "failed": failed}


async def similar_step(run_id: uuid.UUID, config: PolicyAiTask, spend: Spend) -> str:
    async with SessionLocal() as session:
        candidates = await repo.scenario_backlog(session, config.batch_size)
        if not candidates:
            return "没有待找相似的新增场景"
        rows, known = await prompt_rows(session, candidates)
    await update_run(run_id, stage="similar", source_rows=len(candidates))
    status, results = await ask(
        run_id,
        spend,
        prompt_id=config.prompt_id,
        rows=rows,
        caller="政策AI打标·新增场景找相似",
        run_field="scenario_run_id",
    )
    counts = await _save([candidate.id for candidate in candidates], results, known)
    await update_run(run_id, scenario_rows=counts["done"], scenario_failed=counts["failed"])
    note = (
        f"{len(candidates)} 个新增场景{reused_note(status)}，AI 判断了 {counts['done']} 个，失败 {counts['failed']} 个"
    )
    left = sum(1 for result in results if not_run(result))
    if left:
        note += f"；{status.get('error_message') or '任务提前停止'}，{left} 个下批接着判断"
    return note
