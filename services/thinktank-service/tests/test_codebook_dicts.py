"""智库 6 张专属码表拉取、逐键兜底、缓存及资料库动态选项合并与二维范围收敛测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.common import codebook_client
from app.knowledge.application import knowledge, knowledge_write
from app.knowledge.domain.scopes import KnowledgeAccess
from app.knowledge.repositories import knowledge as knowledge_repo


async def test_get_thinktank_dicts_realtime_and_failure_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    mode = {"state": "first"}

    class _Client:
        is_closed = False

        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def get(self, url: str, **_kwargs: Any) -> httpx.Response:
            calls.append(url)
            if mode["state"] == "fail":
                raise httpx.ConnectError("codebook unavailable", request=httpx.Request("GET", url))
            if mode["state"] == "updated":
                return httpx.Response(
                    200,
                    json={"data": {"provinces": ["集团", "广东省", "浙江省"]}},
                    request=httpx.Request("GET", url),
                )
            return httpx.Response(
                200,
                json={
                    "data": {
                        "file_types": ["经分", " 经分 ", "", "自定义类"],
                        "departments": [],  # 空列表回退默认
                        "industries": ["党政", "教育"],
                        "product_types": "not-a-list",  # 非列表回退默认
                        "provinces": ["集团", "广东省"],
                        # market_categories 缺失 -> 回退默认
                    }
                },
                request=httpx.Request("GET", url),
            )

        async def aclose(self) -> None:
            self.is_closed = True

    await codebook_client.close_codebook_client()
    codebook_client.clear_thinktank_dicts_cache()
    monkeypatch.setattr(codebook_client.httpx, "AsyncClient", _Client)
    cfg = SimpleNamespace(
        codebook_base_url="http://codebook:8004/",
        codebook_service_secret="secret",
        codebook_timeout_seconds=1.5,
    )

    first = await codebook_client.get_thinktank_dicts(cfg)
    assert calls == ["http://codebook:8004/internal/v1/thinktank-dicts"]
    assert first["file_types"] == ["经分", "自定义类"]
    assert first["departments"] == list(codebook_client.DEFAULT_THINKTANK_DICTS["departments"])
    assert first["industries"] == ["党政", "教育"]
    assert first["product_types"] == list(codebook_client.DEFAULT_THINKTANK_DICTS["product_types"])
    assert first["provinces"] == ["集团", "广东省"]
    assert first["market_categories"] == ["行客", "商客", "综合", "无"]

    # 码表更新后实时生效（零延迟），且外部修改返回值不污染内部快照
    first["provinces"].append("污染项")
    mode["state"] = "updated"
    second = await codebook_client.get_thinktank_dicts(cfg)
    assert len(calls) == 2
    assert second["provinces"] == ["集团", "广东省", "浙江省"]

    # 码表服务临时不可用时触发短时熔断并回退最近一次成功快照
    mode["state"] = "fail"
    third = await codebook_client.get_thinktank_dicts(cfg)
    assert len(calls) == 3
    assert third["provinces"] == ["集团", "广东省", "浙江省"]
    fourth = await codebook_client.get_thinktank_dicts(cfg)
    assert len(calls) == 3
    assert fourth["provinces"] == ["集团", "广东省", "浙江省"]
    await codebook_client.close_codebook_client()


async def test_knowledge_options_merge_codebooks_and_respect_2d_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        knowledge_repo,
        "preview_options",
        AsyncMock(
            return_value={
                "file_type": {"items": ["产品", "通报"], "truncated": False},
                "depart_affiliation": {"items": ["历史专班"], "truncated": True},
                "industry_type": {"items": ["教育|中小", "金融"], "truncated": False},
                "product_type": {"items": ["云|ICT"], "truncated": False},
                "product_sub_type": {"items": ["智算专线", "云电脑"], "truncated": False},
                "app_scenario": {"items": ["智慧医院"], "truncated": False},
                "market_category": {"items": ["政企"], "truncated": False},
                "prov_name": {"items": ["浙江省"], "truncated": False},
                "data_time": {"items": ["2026/6"], "truncated": False},
            }
        ),
    )
    dicts = {
        "file_types": ["经分", "产品", "通报"],
        "departments": ["政企部", "市场部"],
        "industries": ["党政", "教育", "金融"],
        "product_types": ["云", "网"],
        "provinces": ["集团", "北京市"],
        "market_categories": ["行客", "商客"],
    }
    monkeypatch.setattr(knowledge, "get_thinktank_dicts", AsyncMock(return_value=dicts))

    limited = KnowledgeAccess.from_levels(
        {
            "thinktank.file_type.product": "READ",
            "thinktank.file_type.undefined": "READ",
            "thinktank.industry_type.edu": "READ",
            "thinktank.industry_type.sme": "READ",
        }
    )
    res = await knowledge.get_options(AsyncMock(), access=limited)
    opts = res["options"]

    # file_type 与 industry_type 严格受二维可读范围限制
    assert opts["file_type"]["items"] == ["产品", "未定义"]
    assert opts["industry_type"]["items"] == ["教育", "中小"]
    # 动态码表在前，DB 去重值在后
    assert opts["depart_affiliation"] == {"items": ["政企部", "市场部", "历史专班"], "truncated": True}
    assert opts["product_type"]["items"] == ["云", "网", "ICT"]
    assert opts["prov_name"]["items"] == ["集团", "北京市", "浙江省"]
    assert opts["market_category"]["items"] == ["行客", "商客", "政企"]
    # 非码表项保持原样
    assert opts["operator_type"]["items"] == ["未知", "电信", "联通", "移动"]
    assert opts["product_sub_type"]["items"] == ["智算专线", "云电脑"]

    # options/search 同样合并动态码表 + DB 匹配，且尊重二维范围
    monkeypatch.setattr(knowledge_repo, "search_options", AsyncMock(return_value=["教育|金融"]))
    assert await knowledge.search_options(AsyncMock(), field="industry_type", keyword="", access=limited) == ["教育"]
    assert await knowledge.search_options(AsyncMock(), field="operator_type", keyword="电", access=limited) == ["电信"]

    # 动态码表新增枚举在元数据校验中放行
    assert (
        knowledge_write.validate_metadata_values({"product_type": "低空经济"}, dicts={"product_types": ["低空经济"]})
        == []
    )
    assert knowledge_write.validate_metadata_values({"product_type": "未知产品"}, dicts={"product_types": ["云"]}) != []
