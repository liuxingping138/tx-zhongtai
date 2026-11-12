from __future__ import annotations

import uuid
from datetime import date

from app.crawlconfig.application.expand import ExpandResult
from app.crawlconfig.application.expand_preview import (
    _duplicate_line,
    _moved_line,
    _sheet,
    _site_key,
    _step_line,
    _unknown_line,
)
from app.crawlconfig.domain.expand import CONVERT, ColumnRule, ExpandPlan, Step
from app.policy.domain.models import Source


def _dummy_source(code: str = "32070000001", tag: str = "政策文件") -> Source:
    return Source(
        id=uuid.uuid4(),
        internal_id=uuid.uuid4().hex,
        site_code=code,
        site_name="测试网站",
        province_name="江苏省",
        city_name="连云港市",
        tag=tag,
        url="https://test.gov.cn/old",
    )


def test_expand_preview_lines() -> None:
    source = _dummy_source()
    rule = ColumnRule("R001", "32070000001", "新栏目", "https://test.gov.cn/new", date(2026, 11, 1))
    step = Step(CONVERT, rule, source)

    # 1. _site_key
    assert _site_key(source) == ("测试网站", "江苏省", "连云港市")

    # 2. _step_line
    line = _step_line(step, "", [source])
    assert line[0] == "原来那行改成这个栏目"
    assert line[1] == "R001"
    assert line[3] == "测试网站"

    # 3. _unknown_line
    unknown = _unknown_line(rule)
    assert unknown[0] == "不展开"
    assert "没有这个网站编码" in unknown[-1]

    # 4. _duplicate_line
    dup = _duplicate_line(rule, source)
    assert dup[0] == "不展开"
    assert "只算一个栏目" in dup[-1]

    # 5. _moved_line
    moved = _moved_line(rule, source)
    assert moved[0] == "不动"
    assert "那一行留在原编码下" in moved[-1]


def test_sheet_generation() -> None:
    source = _dummy_source()
    rule = ColumnRule("R001", "32070000001", "新栏目", "https://test.gov.cn/new", date(2026, 11, 1))
    step = Step(CONVERT, rule, source)

    plan = ExpandPlan(
        steps=[step],
        unknown=[rule],
        duplicates=[(rule, source)],
    )
    result = ExpandResult(
        plan=plan,
        conflicts=[(step, "冲突原因")],
        moved=[(rule, source)],
    )

    sites = {_site_key(source): [source]}
    content = _sheet(result, sites)
    assert isinstance(content, bytes)
    assert len(content) > 0
