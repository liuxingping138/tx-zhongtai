"""列表和导出的排序以主键收尾：前面几列相同的行很多（信源按栏目展开后同一网站几行），
OFFSET 翻页时并列行先后不稳定，会重复或漏行；详情页按位置取上一条、下一条也会跳乱。"""

from __future__ import annotations

from app.policy.domain.models import BaseTag, Interpretation, Source
from app.policy.repositories import base_tags, interpretations, sources


def test_every_list_order_ends_with_the_primary_key() -> None:
    for module, model in ((sources, Source), (base_tags, BaseTag), (interpretations, Interpretation)):
        assert module._ORDER[-1] is model.id, module.__name__
