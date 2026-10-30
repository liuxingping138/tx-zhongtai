"""汇总 ORM 模型：导入本模块即把全部表注册到 Base.metadata，供 Alembic 与元数据校验使用。"""

from __future__ import annotations

from app.domain.models import BatchRun, OutboxEvent, PromptTemplate, RunCost, WorkerHeartbeat

__all__ = ["BatchRun", "OutboxEvent", "PromptTemplate", "RunCost", "WorkerHeartbeat"]
