"""筛选输入：日期使用闭区间，查询时转为次日开区间。"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.fields import Status

MAX_STATS_DAYS = 31
MAX_ROUTED_DAYS = 366


class ListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=100)
    project_status: Status = "1"
    project_name: str = Field(default="", max_length=256)
    project_content_id: str = Field(default="", max_length=255)
    purchaser_provname: list[str] = Field(default_factory=list, max_length=40)
    purchaser_cityname: list[str] = Field(default_factory=list, max_length=100)
    purchaser_countyname: list[str] = Field(default_factory=list, max_length=100)
    is_supp_scene: list[Literal["0", "1"]] = Field(default_factory=list)
    collect_date_from: date | None = None
    collect_date_to: date | None = None
    public_date_from: date | None = None
    public_date_to: date | None = None
    create_time_from: date | None = None
    create_time_to: date | None = None

    def _has_bounded_date(self) -> bool:
        for field in ("collect_date", "public_date", "create_time"):
            start, end = getattr(self, f"{field}_from"), getattr(self, f"{field}_to")
            if start and end and (end - start).days < MAX_ROUTED_DAYS:
                return True
        return False

    @model_validator(mode="after")
    def date_order(self) -> "ListQuery":
        for field in ("collect_date", "public_date", "create_time"):
            start, end = getattr(self, f"{field}_from"), getattr(self, f"{field}_to")
            if start and end and start > end:
                raise ValueError("开始日期不能晚于结束日期")
            if end == date.max:
                raise ValueError("结束日期超出支持范围")
        if self.project_name.strip() and not self._has_bounded_date():
            raise ValueError("按项目名称查询时请先选择完整的日期范围（建议选择采集时间，且跨度不超过 366 天）")
        return self


class StatsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def date_order(self) -> "StatsQuery":
        if not 0 <= (self.date_to - self.date_from).days < MAX_STATS_DAYS:
            raise ValueError("请选择不超过 31 天的有效日期范围")
        if self.date_to == date.max:
            raise ValueError("结束日期超出支持范围")
        return self
