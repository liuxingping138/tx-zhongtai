"""智库访问 IP 白名单表。"""

from __future__ import annotations

import uuid
from datetime import datetime

from platform_common.orm_base import Base
from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class IpWhitelistEntry(Base):
    """公司网络以外的地方访问智库，要管理员在这里给那个 IP 开一条有到期时间的白名单。"""

    __tablename__ = "thinktank_ip_whitelist"
    __table_args__ = (
        Index("ix_thinktank_ipw_expires_at", "expires_at"),
        {"comment": "智库访问IP白名单"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="主键")
    ip_range: Mapped[str] = mapped_column(String(64), nullable=False, comment="IP或网段")
    holder: Mapped[str] = mapped_column(String(64), nullable=False, comment="使用人")
    reason: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="", comment="开通原因")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="到期时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="开通人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="开通人")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="开通时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="最后修改人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="最后修改人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最后修改时间")
