"""智库统计仓储统一出口。"""

from app.statistics.repositories.overview import (
    BehaviorSummary,
    LibraryAssetSummary,
    ProposalWinSummary,
    TrendBucket,
    fetch_behavior_summary,
    fetch_dimension_raw_counts,
    fetch_library_totals,
    fetch_proposal_win_summary,
    fetch_trend_series,
)
from app.statistics.repositories.rankings import (
    DocumentActivityItem,
    DocumentPeekData,
    RankedActor,
    RankedDepartment,
    RankedDocument,
    fetch_document_peek,
    fetch_top_actors,
    fetch_top_departments,
    fetch_top_documents_by_metrics,
)

__all__ = [
    "BehaviorSummary",
    "DocumentActivityItem",
    "DocumentPeekData",
    "LibraryAssetSummary",
    "ProposalWinSummary",
    "RankedActor",
    "RankedDepartment",
    "RankedDocument",
    "TrendBucket",
    "fetch_behavior_summary",
    "fetch_dimension_raw_counts",
    "fetch_document_peek",
    "fetch_library_totals",
    "fetch_proposal_win_summary",
    "fetch_top_actors",
    "fetch_top_departments",
    "fetch_top_documents_by_metrics",
    "fetch_trend_series",
]
