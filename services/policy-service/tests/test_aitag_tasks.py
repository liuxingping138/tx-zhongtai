"""政策 AI 打标三个任务和任务调度编码的对应关系。"""

from __future__ import annotations

from app.aitag.domain.tasks import TASKS, job_code, task_of
from app.scheduler.domain.scheduling import JOBS, TIMEOUTS


def test_each_tagging_task_is_its_own_scheduled_job_in_page_order() -> None:
    assert list(JOBS) == ["crawler", "policy_ai_type", "policy_ai_interpret", "policy_ai_opportunity"]
    assert [JOBS[job_code(task)] for task in TASKS] == ["政策类型判断", "政策解读", "政策市场机会"]
    assert all(TIMEOUTS[job_code(task)] == 6 * 3600 for task in TASKS)


def test_job_codes_map_back_to_tasks_and_nothing_else() -> None:
    assert [task_of(job_code(task)) for task in TASKS] == list(TASKS)
    assert task_of("crawler") is None and task_of("policy_ai") is None and task_of("policy_ai_other") is None
