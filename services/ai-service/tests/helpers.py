"""单测共用的假对象：不连数据库，仓储函数由各用例 monkeypatch。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from platform_common.actors import Actor

from app.domain.models import BatchRun, PromptTemplate

ACTOR = Actor(id="u1", name="测试员")
NOW = datetime(2026, 10, 15, 3, 0, tzinfo=UTC)
PROMPT_ID = "a" * 32
RUN_ID = "b" * 32


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


def template(**overrides: Any) -> PromptTemplate:
    values: dict[str, Any] = {
        "id": PROMPT_ID,
        "title": "企业行业",
        "content": "企业：@【名称】",
        "output_fields": "行业",
        "model_id": "baidu-deepseek-v3.2",
        "excel_name": "",
        "excel_rows": 0,
        "excel_headers": [],
        "code_name": "",
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


def run(**overrides: Any) -> BatchRun:
    values: dict[str, Any] = {
        "id": RUN_ID,
        "prompt_id": PROMPT_ID,
        "prompt_title": "企业行业",
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
