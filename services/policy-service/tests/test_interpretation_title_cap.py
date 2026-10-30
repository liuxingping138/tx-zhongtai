"""解读的「政策原文名称」有 btree 索引（列表默认按它排），单条索引项约 2704 字节封顶：
源库把整段脚本当标题的一写进去整批回滚，解读任务从此卡在队头。页面、导入超长就提示，AI 写入时截断。"""

from __future__ import annotations

from types import SimpleNamespace

from app.aitag.application import interpreting
from app.policy.application import interpretations
from app.policy.domain.fields import DATA_STATUS_PENDING, POLICY_TITLE_MAX


def test_an_overlong_title_is_reported_instead_of_breaking_the_write() -> None:
    values = {"data_status": DATA_STATUS_PENDING, "policy_title": "标" * (POLICY_TITLE_MAX + 1)}
    assert interpretations._write_error(values) == f"政策原文名称超过 {POLICY_TITLE_MAX} 字"
    values["policy_title"] = "标" * POLICY_TITLE_MAX
    assert interpretations._write_error(values) is None


def test_ai_interpretation_rows_cut_the_title() -> None:
    tag = SimpleNamespace(policy_name="脚" * 2000, source_content_id="c1")
    row = interpreting._new_row(tag, {}, "k1")  # type: ignore[arg-type]
    assert len(row.policy_title) == POLICY_TITLE_MAX
    assert len(row.policy_title.encode()) < 2704
