"""报告库与方案库元数据规格：列定义、筛选类型、码表映射、导出表头与校验规则。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platform_common.columns import ColumnSpec, string_lengths

from app.library.domain.models import (
    ProposalFavorite,
    ProposalFile,
    ProposalOpLog,
    ReportFavorite,
    ReportFile,
    ReportOpLog,
)


@dataclass(frozen=True)
class LibrarySpec:
    """描述一个标准智库子库（报告库 / 方案库）的完整领域配置。"""

    slug: str
    label: str
    item_noun: str
    resource: str
    event_prefix: str
    storage_prefix: str
    file_model: type[Any]
    favorite_model: type[Any]
    log_model: type[Any]
    title_field: str
    category_field: str
    defined_fields: tuple[str, ...]
    pipe_fields: frozenset[str]
    business_fields: tuple[str, ...]
    editable_fields: tuple[str, ...]
    filter_kinds: dict[str, str]
    option_fields: tuple[str, ...]
    codebook_option_map: dict[str, str]
    static_options: dict[str, tuple[str, ...]]
    export_columns: tuple[ColumnSpec, ...]
    undefined_columns: tuple[ColumnSpec, ...]
    tag_writable_fields: tuple[str, ...]
    summary_fields: tuple[tuple[str, str], ...]
    export_filename: str
    undefined_filename: str
    skip_filename: str
    sheet_name: str
    tag_subject: str
    missing_upload_msg: str
    not_found_msg: str
    fallback_stem: str

    def column(self, field: str) -> Any:
        return getattr(self.file_model, field)

    def option_columns(self) -> dict[str, Any]:
        return {field: self.column(field) for field in self.option_fields}

    def field_lengths(self) -> dict[str, int]:
        return string_lengths(self.file_model)

    def is_defined_values(self, row: Any) -> bool:
        return any(bool(str(getattr(row, field, "") or "").strip()) for field in self.defined_fields)


REPORT_BUSINESS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("report_name", "报告名称"),
    ColumnSpec("project_name", "所属项目"),
    ColumnSpec("customer_name", "客户名称"),
    ColumnSpec("report_type", "报告类型"),
    ColumnSpec("industry_tags", "行业赛道标签"),
    ColumnSpec("region_tag", "区域标签"),
    ColumnSpec("delivery_dept", "交付部门"),
    ColumnSpec("participants", "参与人员"),
    ColumnSpec("is_temp_support", "是否临时支撑"),
    ColumnSpec("delivery_date", "交付日期"),
    ColumnSpec("summary", "核心结论摘要(≤100字)"),
    ColumnSpec("keywords", "关键词(3-5个)"),
    ColumnSpec("data_sources", "主要数据来源"),
)

REPORT_SPEC = LibrarySpec(
    slug="reports",
    label="报告库",
    item_noun="报告",
    resource="thinktank.reports",
    event_prefix="thinktank.reports",
    storage_prefix="reports",
    file_model=ReportFile,
    favorite_model=ReportFavorite,
    log_model=ReportOpLog,
    title_field="report_name",
    category_field="report_type",
    defined_fields=("report_type", "industry_tags"),
    pipe_fields=frozenset({"industry_tags"}),
    business_fields=tuple(col.field for col in REPORT_BUSINESS_COLUMNS),
    editable_fields=(*(col.field for col in REPORT_BUSINESS_COLUMNS), "remark"),
    filter_kinds={
        "report_name": "keyword",
        "project_name": "keyword",
        "customer_name": "keyword",
        "report_type": "exact",
        "industry_tags": "pipe",
        "region_tag": "exact",
        "delivery_dept": "keyword",
        "participants": "keyword",
        "is_temp_support": "exact",
        "delivery_date": "keyword",
        "keywords": "keyword",
        "tag_status": "tag_status",
        "favorite_only": "favorite_only",
    },
    option_fields=(
        "project_name",
        "customer_name",
        "report_type",
        "industry_tags",
        "region_tag",
        "delivery_dept",
        "participants",
        "is_temp_support",
        "delivery_date",
        "keywords",
    ),
    codebook_option_map={
        "industry_tags": "industries",
        "region_tag": "provinces",
        "delivery_dept": "departments",
    },
    static_options={
        "is_temp_support": ("是", "否"),
        "tag_status": ("已定义", "未定义"),
        "favorite_only": ("仅看收藏",),
    },
    export_columns=(
        *REPORT_BUSINESS_COLUMNS,
        ColumnSpec("uploaded_at", "上传时间"),
        ColumnSpec("file_suffix", "文件后缀"),
        ColumnSpec("file_size_display", "文件大小"),
    ),
    undefined_columns=(
        ColumnSpec("id", "文件ID"),
        *REPORT_BUSINESS_COLUMNS,
        ColumnSpec("file_suffix", "文件后缀"),
        ColumnSpec("uploaded_at", "上传时间"),
        ColumnSpec("remark", "备注"),
    ),
    tag_writable_fields=(*(col.field for col in REPORT_BUSINESS_COLUMNS if col.field != "report_name"), "remark"),
    summary_fields=tuple((col.field, col.header) for col in REPORT_BUSINESS_COLUMNS),
    export_filename="报告库.xlsx",
    undefined_filename="报告库未定义数据.xlsx",
    skip_filename="报告库标签-跳过明细.xlsx",
    sheet_name="报告库",
    tag_subject="报告标签",
    missing_upload_msg="请上传报告文件",
    not_found_msg="报告文件不存在",
    fallback_stem="report-file",
)

PROPOSAL_BUSINESS_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("proposal_name", "方案名称"),
    ColumnSpec("customer_name", "客户名称"),
    ColumnSpec("proposal_type", "方案类型"),
    ColumnSpec("industry_tags", "行业赛道标签"),
    ColumnSpec("region_tag", "区域标签"),
    ColumnSpec("opportunity_source", "商机来源"),
    ColumnSpec("bidding_method", "招标方式"),
    ColumnSpec("bid_deadline", "投标截止日期"),
    ColumnSpec("owner_dept", "方案负责部门"),
    ColumnSpec("owner_name", "方案负责人"),
    ColumnSpec("quote_amount", "报价(万元)"),
    ColumnSpec("result_status", "结果"),
    ColumnSpec("win_amount", "中标金额(万元)"),
    ColumnSpec("selling_points", "方案核心卖点摘要(≤100字)"),
)

PROPOSAL_SPEC = LibrarySpec(
    slug="proposals",
    label="方案库",
    item_noun="方案",
    resource="thinktank.proposals",
    event_prefix="thinktank.proposals",
    storage_prefix="proposals",
    file_model=ProposalFile,
    favorite_model=ProposalFavorite,
    log_model=ProposalOpLog,
    title_field="proposal_name",
    category_field="proposal_type",
    defined_fields=("proposal_type", "industry_tags"),
    pipe_fields=frozenset({"industry_tags"}),
    business_fields=tuple(col.field for col in PROPOSAL_BUSINESS_COLUMNS),
    editable_fields=(*(col.field for col in PROPOSAL_BUSINESS_COLUMNS), "remark"),
    filter_kinds={
        "proposal_name": "keyword",
        "customer_name": "keyword",
        "proposal_type": "exact",
        "industry_tags": "pipe",
        "region_tag": "exact",
        "opportunity_source": "exact",
        "bidding_method": "exact",
        "bid_deadline": "keyword",
        "owner_dept": "keyword",
        "owner_name": "keyword",
        "result_status": "exact",
        "tag_status": "tag_status",
        "favorite_only": "favorite_only",
    },
    option_fields=(
        "customer_name",
        "proposal_type",
        "industry_tags",
        "region_tag",
        "opportunity_source",
        "bidding_method",
        "bid_deadline",
        "owner_dept",
        "owner_name",
        "result_status",
    ),
    codebook_option_map={
        "industry_tags": "industries",
        "region_tag": "provinces",
        "owner_dept": "departments",
    },
    static_options={
        "result_status": ("中标", "未中标", "待定", "流标"),
        "tag_status": ("已定义", "未定义"),
        "favorite_only": ("仅看收藏",),
    },
    export_columns=(
        *PROPOSAL_BUSINESS_COLUMNS,
        ColumnSpec("uploaded_at", "上传时间"),
        ColumnSpec("file_suffix", "文件后缀"),
        ColumnSpec("file_size_display", "文件大小"),
    ),
    undefined_columns=(
        ColumnSpec("id", "文件ID"),
        *PROPOSAL_BUSINESS_COLUMNS,
        ColumnSpec("file_suffix", "文件后缀"),
        ColumnSpec("uploaded_at", "上传时间"),
        ColumnSpec("remark", "备注"),
    ),
    tag_writable_fields=(*(col.field for col in PROPOSAL_BUSINESS_COLUMNS if col.field != "proposal_name"), "remark"),
    summary_fields=tuple((col.field, col.header) for col in PROPOSAL_BUSINESS_COLUMNS),
    export_filename="方案库.xlsx",
    undefined_filename="方案库未定义数据.xlsx",
    skip_filename="方案库标签-跳过明细.xlsx",
    sheet_name="方案库",
    tag_subject="方案标签",
    missing_upload_msg="请上传方案文件",
    not_found_msg="方案文件不存在",
    fallback_stem="proposal-file",
)

LIBRARY_SPECS: dict[str, LibrarySpec] = {
    REPORT_SPEC.slug: REPORT_SPEC,
    PROPOSAL_SPEC.slug: PROPOSAL_SPEC,
}
