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
from app.domain.fields import AREA_CODE_COLUMNS, POLICY_TYPE_COLUMNS, SCENARIO_COLUMNS


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def content_hash(values: dict[str, str], fields: tuple[str, ...]) -> str:
    payload = {key: values.get(key, "") for key in fields}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class PolicyType(Base):
    __tablename__ = "codebook_policy_types"
    __table_args__ = (UniqueConstraint("type_name", name="uq_codebook_policy_types_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    seq_no: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    type_name: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False)


class Scenario(Base):
    __tablename__ = "codebook_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    industry_scenario_code: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    industry_code: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    industry_l1: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    industry_l2: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    industry_l3: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    scenario_tag: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    scenario_level: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    scenario_type: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    desc_90: Mapped[str] = mapped_column(Text, nullable=False, default="")
    desc_130: Mapped[str] = mapped_column(Text, nullable=False, default="")
    desc_pest: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scenario_source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scenario_hierarchy: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    scenario_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    scenario_l1_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    scenario_l1_desc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scenario_l2_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    scenario_l2_desc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scenario_l3_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    scenario_l3_desc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    customer_group_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    customer_group_industry: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    org_keywords: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope_keywords: Mapped[str] = mapped_column(Text, nullable=False, default="")
    customer_level: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    customer_category: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    product_l1_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    product_l2_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    branch_count: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    product_l1_sort: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    product_l2_sort: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False)

    def business_values(self) -> dict[str, str]:
        return {spec.field: str(getattr(self, spec.field) or "") for spec in SCENARIO_COLUMNS}

    def refresh_hash(self) -> None:
        self.content_hash = content_hash(self.business_values(), tuple(spec.field for spec in SCENARIO_COLUMNS))


class AreaCode(Base):
    __tablename__ = "codebook_area_codes"
    __table_args__ = (UniqueConstraint("county_id", name="uq_codebook_area_codes_county_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    prov_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    prov_name: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True)
    city_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    city_name: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True)
    county_id: Mapped[str] = mapped_column(String(64), nullable=False)
    county_name: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True)
    alias_prov_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    alias_city_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    alias_county_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    city_name_short: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    county_name_short: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False)

    def business_values(self) -> dict[str, str]:
        return {spec.field: str(getattr(self, spec.field) or "") for spec in AREA_CODE_COLUMNS}


class OutboxEvent(Base):
    __tablename__ = "codebook_outbox"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


POLICY_TYPE_FIELDS = tuple(spec.field for spec in POLICY_TYPE_COLUMNS)
SCENARIO_FIELDS = tuple(spec.field for spec in SCENARIO_COLUMNS)
AREA_CODE_FIELDS = tuple(spec.field for spec in AREA_CODE_COLUMNS)
