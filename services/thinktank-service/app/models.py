"""汇总智库服务全部 ORM 表，供 Alembic 迁移发现元数据。"""

from __future__ import annotations

from app.common.models import OutboxEvent
from app.knowledge.domain.models import KnowledgeFavorite, KnowledgeFile, KnowledgeOpLog
from app.library.domain.models import (
    ProposalFavorite,
    ProposalFile,
    ProposalOpLog,
    ReportFavorite,
    ReportFile,
    ReportOpLog,
)

__all__ = [
    "KnowledgeFavorite",
    "KnowledgeFile",
    "KnowledgeOpLog",
    "OutboxEvent",
    "ProposalFavorite",
    "ProposalFile",
    "ProposalOpLog",
    "ReportFavorite",
    "ReportFile",
    "ReportOpLog",
]
