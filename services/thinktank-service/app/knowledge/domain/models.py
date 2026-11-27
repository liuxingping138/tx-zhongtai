"""知识库 ORM 模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

from platform_common.orm_base import Base
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class KnowledgeFile(Base):
    __tablename__ = "thinktank_knowledge_files"
    __table_args__ = (
        Index("ix_thinktank_kf_file_type", "file_type"),
        Index("ix_thinktank_kf_industry_type", "industry_type"),
        Index("ix_thinktank_kf_operator_type", "operator_type"),
        Index("ix_thinktank_kf_prov_name", "prov_name"),
        Index("ix_thinktank_kf_market_category", "market_category"),
        Index("ix_thinktank_kf_is_defined", "is_defined"),
        Index("ix_thinktank_kf_uploaded_at", "uploaded_at"),
        {"comment": "智库知识库资料"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    file_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True, comment="资料名称")
    file_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default="", comment="文件类型"
    )
    operator_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default="", comment="运营商类型"
    )
    depart_affiliation: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="部门归属"
    )
    industry_type: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="行业类型"
    )
    app_scenario: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default="", comment="应用场景"
    )
    market_category: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default="", comment="市场类别"
    )
    product_type: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="产品类型"
    )
    product_sub_type: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default="", comment="产品子类型"
    )
    prov_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="", comment="省份")
    data_time: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default="", comment="资料时间"
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="上传时间")
    file_suffix: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default="", comment="文件后缀"
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0", comment="文件大小字节"
    )
    storage_path: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default="", comment="文件存储路径"
    )
    content_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="摘要与预览文本"
    )
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="", comment="备注")
    is_defined: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", comment="是否已定义标签"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1", comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")


class KnowledgeFavorite(Base):
    __tablename__ = "thinktank_knowledge_favorites"
    __table_args__ = {"comment": "知识库收藏"}

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="用户ID")
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thinktank_knowledge_files.id", ondelete="CASCADE"),
        primary_key=True,
        comment="资料ID",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="收藏时间")


class KnowledgeOpLog(Base):
    __tablename__ = "thinktank_knowledge_logs"
    __table_args__ = (
        Index("ix_thinktank_kl_file_created", "file_id", "created_at"),
        Index("ix_thinktank_kl_created_op", "created_at", "op_type"),
        {"comment": "知识库文件操作日志"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thinktank_knowledge_files.id", ondelete="CASCADE"),
        nullable=False,
        comment="资料ID",
    )
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="操作人ID")
    actor_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")
    op_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="操作类型")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="", comment="操作明细")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="操作时间")
