"""单测共用的假对象：不连数据库，仓储函数由各用例 monkeypatch。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from platform_common.actors import Actor

from app.domain.models import AiModel, BatchRun, PromptTemplate, TemplateRelease

ACTOR = Actor(id="u1", name="测试员")
NOW = datetime(2026, 10, 15, 3, 0, tzinfo=UTC)
PROMPT_ID = "a" * 32
RUN_ID = "b" * 32
RELEASE_ID = "c" * 32


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.executed: list[Any] = []
        self.commits = 0

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def execute(self, statement: Any) -> None:
        self.executed.append(statement)

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def ai_model(**overrides: Any) -> AiModel:
    values: dict[str, Any] = {
        "id": "deepseek-v4-flash",
        "name": "字节-DeepSeek-V4-Flash（联网）",
        "provider": "ark",
        "endpoint": "ep-flash",
        "web_search": True,
        "thinking": "enabled",
        "reasoning_effort": "low",
        "service_tier": "flex",
        "input_price": Decimal("0.003"),
        "output_price": Decimal("0.009"),
        "flex_input_price": Decimal("0.0015"),
        "flex_output_price": Decimal("0.0045"),
        "peak_input_price": None,
        "peak_output_price": None,
        "peak_hours": "",
        "search_price": Decimal("0.004"),
        "rate_limit": "",
        "enabled": True,
        "sort_order": 10,
        "version": 1,
        "created_at": NOW,
        "created_by_name": "系统",
        "updated_at": NOW,
        "updated_by_name": "系统",
    }
    values.update(overrides)
    return AiModel(**values)


def sample_models() -> list[AiModel]:
    """单测里库中的模型：方舟 Flash（联网、低优）和千帆 V3.2（思考可选）。"""

    return [
        ai_model(),
        ai_model(
            id="baidu-deepseek-v3.2",
            name="百度-DeepSeek-V3.2",
            provider="baidu",
            endpoint="deepseek-v3.2",
            web_search=False,
            thinking="switch",
            reasoning_effort="",
            service_tier="",
            input_price=Decimal("0.001"),
            output_price=Decimal("0.005"),
            flex_input_price=None,
            flex_output_price=None,
            search_price=Decimal(0),
            sort_order=20,
        ),
    ]


def template(**overrides: Any) -> PromptTemplate:
    values: dict[str, Any] = {
        "id": PROMPT_ID,
        "title": "企业行业",
        "category": "policy",
        "content": "企业：@【名称】",
        "output_fields": "行业",
        "model_id": "baidu-deepseek-v3.2",
        "excel_name": "",
        "excel_rows": 0,
        "excel_headers": [],
        "code_name": "",
        "code_table": "",
        "release_id": None,
        "version": 1,
        "created_at": NOW,
        "created_by_id": "u1",
        "created_by_name": "测试员",
        "updated_at": NOW,
        "updated_by_id": "u1",
        "updated_by_name": "测试员",
    }
    values.update(overrides)
    return PromptTemplate(**values)


def release(**overrides: Any) -> TemplateRelease:
    """模板 template() 上线的第 3 版。"""

    values: dict[str, Any] = {
        "id": RELEASE_ID,
        "prompt_id": PROMPT_ID,
        "release_no": 3,
        "title": "企业行业",
        "category": "policy",
        "content": "企业：@【名称】",
        "output_fields": "行业",
        "model_id": "baidu-deepseek-v3.2",
        "code_table": "",
        "code_name": "",
        "released_at": NOW,
        "released_by_id": "u1",
        "released_by_name": "管理员",
    }
    values.update(overrides)
    return TemplateRelease(**values)


def run(**overrides: Any) -> BatchRun:
    values: dict[str, Any] = {
        "id": RUN_ID,
        "prompt_id": PROMPT_ID,
        "prompt_title": "企业行业",
        "prompt_category": "policy",
        "prompt_content": "企业：@【名称】",
        "output_fields": "行业",
        "model_id": "baidu-deepseek-v3.2",
        "model_name": "百度-DeepSeek-V3.2",
        "thinking": False,
        "row_limit": 0,
        "status": "queued",
        "total_count": 0,
        "done_count": 0,
        "failed_count": 0,
        "format_failed_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "search_calls": 0,
        "inference_cost": 0,
        "search_cost": 0,
        "cancel_requested": False,
        "heartbeat_at": None,
        "error_message": "",
        "started_at": None,
        "finished_at": None,
        "created_at": NOW,
        "created_by_id": "u1",
        "created_by_name": "测试员",
        "source": "manual",
        "release_no": None,
        "input_name": "",
    }
    values.update(overrides)
    return BatchRun(**values)


def xlsx(rows: list[list[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def fake_stream(events: list[dict[str, Any]]) -> Any:
    async def stream(*_: Any, **__: Any) -> AsyncIterator[dict[str, Any]]:
        for event in events:
            yield event

    return stream


async def noop(*_: Any, **__: Any) -> None:
    return None
