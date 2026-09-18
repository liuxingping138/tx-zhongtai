from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm_base import Base
from app.domain.fields import BASE_TAG_COLUMNS


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def content_hash(values: dict[str, str], fields: tuple[str, ...]) -> str:
    payload = {key: values.get(key, "") for key in fields}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class Source(Base):
    __tablename__ = "policy_sources"
    __table_args__ = (
        UniqueConstraint("internal_id", name="uq_policy_sources_internal_id"),
        UniqueConstraint("site_code", name="uq_policy_sources_site_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    internal_id: Mapped[str] = mapped_column(String(32), nullable=False)
    site_code: Mapped[str] = mapped_column(String(16), nullable=False)
    province_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    province_code: Mapped[str] = mapped_column(String(8), nullable=False, default="", index=True)
    city_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    city_code: Mapped[str] = mapped_column(String(8), nullable=False, default="", index=True)
    district_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    district_code: Mapped[str] = mapped_column(String(8), nullable=False, default="", index=True)
    site_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    crawl_priority: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tag: Mapped[str] = mapped_column(Text, nullable=False, default="")
    data_type: Mapped[str] = mapped_column(Text, nullable=False, default="")
    department: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False)


class BaseTag(Base):
    __tablename__ = "policy_base_tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    policy_name: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True)
    issuing_dept: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    issuer_industry: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    policy_level: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    province_code: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    province_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    city_code: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    city_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    issued_at: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    policy_types: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_penetrate: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    penetrate_words: Mapped[str] = mapped_column(Text, nullable=False, default="")
    penetrate_score: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    need_interpret: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False)

    def business_values(self) -> dict[str, str]:
        return {spec.field: str(getattr(self, spec.field) or "") for spec in BASE_TAG_COLUMNS}

    def refresh_hash(self) -> None:
        self.content_hash = content_hash(self.business_values(), tuple(spec.field for spec in BASE_TAG_COLUMNS))


class Interpretation(Base):
    __tablename__ = "policy_interpretations"
    __table_args__ = (UniqueConstraint("relation_key", name="uq_policy_interpretations_relation_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    record_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    policy_uid: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    policy_title: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True)
    industry_scenario_code: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    industry_code: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    industry_l1: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    industry_l2: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    industry_l3: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    scenario_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    scenario_l1_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    scenario_l2_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    scenario_l3_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    target_customers: Mapped[str] = mapped_column(Text, nullable=False, default="")
    relation_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    opportunity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    policy_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    has_subsidy: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    subsidy_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    market_opportunity: Mapped[str] = mapped_column(Text, nullable=False, default="")
    info_level: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    is_new_scenario: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    new_scenario_level: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False)


class OutboxEvent(Base):
    __tablename__ = "policy_outbox"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


SOURCE_FIELDS = (
    "province_name",
    "province_code",
    "city_name",
    "city_code",
    "district_name",
    "district_code",
    "site_name",
    "crawl_priority",
    "url",
    "tag",
    "data_type",
    "department",
)
BASE_TAG_FIELDS = tuple(spec.field for spec in BASE_TAG_COLUMNS)
INTERPRETATION_WRITE_FIELDS = (
    "tenant_id",
    "policy_uid",
    "policy_title",
    "industry_scenario_code",
    "industry_code",
    "industry_l1",
    "industry_l2",
    "industry_l3",
    "scenario_code",
    "scenario_l1_name",
    "scenario_l2_name",
    "scenario_l3_name",
    "target_customers",
    "opportunity_type",
    "policy_summary",
    "has_subsidy",
    "subsidy_content",
    "market_opportunity",
    "info_level",
    "is_new_scenario",
    "new_scenario_level",
)
