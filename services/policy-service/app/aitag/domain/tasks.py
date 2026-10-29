"""政策 AI 打标的三个任务。每个在任务调度里是一个独立任务，各自定时、各自手动执行。

类型判断从源库读新政策写基础标签；解读只做「是否解读 = 是」还没解读的；市场机会只做解读过还没补的。
前一个任务没跑，后一个就没有待办，不需要彼此串起来。
"""

from __future__ import annotations

TASKS: dict[str, str] = {"type": "政策类型判断", "interpret": "政策解读", "opportunity": "政策市场机会"}
# 任务调度里的任务编码 = 前缀 + 任务编码。
JOB_PREFIX = "policy_ai_"
# 每个任务的费用记在批次的哪一列。拆分前三步合跑的旧批次，按这一列也能拆回各任务。
TASK_COST = {"type": "type_cost", "interpret": "interpret_cost", "opportunity": "opportunity_cost"}


def job_code(task: str) -> str:
    return JOB_PREFIX + task


# 会花钱的操作（改任务设置和每日费用上限、启用或改时间、立即执行）单独授权：IAM 资源「政策AI打标」，只有完整档。
AI_TAGGING_RESOURCE = "policy.ai_tagging"
