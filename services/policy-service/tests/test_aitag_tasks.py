"""政策 AI 打标三个任务和任务调度编码的对应关系。"""

from __future__ import annotations

from app.aitag.domain.tasks import TASKS, job_code


def test_each_task_has_its_own_job_code() -> None:
    assert [job_code(task) for task in TASKS] == [
        "policy_ai_type",
        "policy_ai_interpret",
        "policy_ai_opportunity",
        "policy_ai_scenario",
    ]
