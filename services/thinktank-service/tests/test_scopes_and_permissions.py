"""权限范围模型（按文件类型 + 行业类型正交校验）、存储工具与种子初始化测试。"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import PermissionDeniedError

from app.core import storage
from app.knowledge.application import seed_data
from app.knowledge.domain.scopes import (
    FILE_TYPE_ITEMS,
    INDUSTRY_TYPE_ITEMS,
    KnowledgeAccess,
    effective_industry_tags,
    normalize_file_type_input,
    split_multi_tags,
)


def test_tag_helpers() -> None:
    assert split_multi_tags(None) == []
    assert split_multi_tags("中小| 教育 | ") == ["中小", "教育"]
    assert effective_industry_tags("") == ["无"]
    assert effective_industry_tags("党政|教育") == ["党政", "教育"]
    assert normalize_file_type_input("未定义") == ""
    assert normalize_file_type_input(" 产品 ") == "产品"


def test_access_levels_orthogonal_file_type_and_industry() -> None:
    access = KnowledgeAccess.from_levels(
        {
            "thinktank.file_type.product": "READ",
            "thinktank.file_type.jingfen": "EXPORT",
            "thinktank.file_type.undefined": "FULL",
            "thinktank.industry_type.edu": "READ",
            "thinktank.industry_type.gov": "FULL",
            "thinktank.industry_type.none": "EXPORT",
        }
    )

    # 文件类型 READ + 行业 READ -> 可读不可导/编
    assert access.can_read_record("产品", "教育") is True
    assert access.can_export_record("产品", "教育") is False
    assert access.can_edit_record("产品", "教育") is False

    # 竖线多行业命中其一即可读；目标动作档位取两个维度的交集能力
    assert access.can_read_record("经分", "中小|教育") is True
    assert access.can_export_record("经分", "中小|教育") is False
    assert access.can_export_record("经分", "") is True  # 空行业视为「无」（EXPORT）
    assert access.can_edit_record("经分", "党政") is False  # 文件类型仅 EXPORT
    assert access.can_edit_record("", "党政") is True  # 未定义 FULL + 党政 FULL
    # 多选行业：读取只需命中其一（any），编辑/上传/删除必须全部行业均有 FULL（all）
    assert access.can_read_record("", "党政|教育") is True
    assert access.can_edit_record("", "党政|教育") is False

    # 当子库菜单档位为 READ 时，数据范围档位被封顶在 READ
    capped = KnowledgeAccess.from_levels(
        {"thinktank.file_type.undefined": "FULL", "thinktank.industry_type.gov": "FULL"},
        module_level="READ",
    )
    assert capped.can_read_record("", "党政") is True
    assert capped.can_export_record("", "党政") is False
    assert capped.can_edit_record("", "党政") is False

    # 未授权维度拒绝并给出可读信息
    assert access.can_read_record("通报", "党政") is False
    with pytest.raises(PermissionDeniedError, match="通报 / 党政"):
        access.require_read("通报", "党政")
    with pytest.raises(PermissionDeniedError, match="产品 / 教育"):
        access.require_export("产品", "教育")
    with pytest.raises(PermissionDeniedError, match="未定义 / 无"):
        access.require_edit("", "")

    summary = access.to_summary()
    assert summary["readable_file_types"] == ["产品", "经分", "未定义"]
    assert summary["exportable_file_types"] == ["经分", "未定义"]
    assert summary["editable_file_types"] == ["未定义"]
    assert summary["readable_industries"] == ["党政", "教育", "无"]
    assert len(FILE_TYPE_ITEMS) == 16
    assert len(INDUSTRY_TYPE_ITEMS) == 12


async def test_storage_save_read_delete_and_path_traversal(tmp_path: Path) -> None:
    assert storage.raw_extension("测试.pptx") == "PPTX"
    assert storage.normalize_suffix("测试.pptx") == "PPT"
    assert storage.normalize_suffix("报表.xlsx") == "EXCEL"
    assert storage.media_type_for_file("测试.pdf", "PDF") == "application/pdf"
    legacy_key = storage.legacy_object_key("demo.pdf", 1024, "pdf")
    assert legacy_key.startswith("knowledgeBase/")
    fid = uuid.uuid4()
    managed_key = storage.new_object_key(fid, "pdf")
    assert storage.is_managed_object_key(managed_key, fid) is True
    assert storage.is_managed_object_key(legacy_key, fid) is False
    assert storage.is_managed_object_key("", fid) is False

    await storage.save_bytes(str(tmp_path), "knowledge/sample.pdf", b"%PDF-1.4")
    assert await storage.read_bytes(str(tmp_path), "knowledge/sample.pdf") == b"%PDF-1.4"
    assert await storage.read_bytes(str(tmp_path), "") is None
    with pytest.raises(ValueError, match="非法存储路径"):
        await storage.read_bytes(str(tmp_path), "../../etc/passwd")

    await storage.delete_file(str(tmp_path), "knowledge/sample.pdf")
    assert await storage.read_bytes(str(tmp_path), "knowledge/sample.pdf") is None
    with pytest.raises(ValueError, match="非法存储路径"):
        await storage.save_bytes(str(tmp_path), "../escape.txt", b"x")

    # MinIO 未配置时 save_object / read_object / delete_object 回退本地存储
    local_cfg = SimpleNamespace(
        storage_dir=str(tmp_path),
        minio_endpoint="",
        minio_access_key="",
        minio_secret_key="",
        minio_bucket="",
        minio_region="us-east-1",
        minio_timeout_seconds=5.0,
    )
    await storage.save_object(local_cfg, "knowledgeBase/test.pdf", b"%PDF-1.7", content_type="application/pdf")
    assert await storage.read_object(local_cfg, "knowledgeBase/test.pdf") == b"%PDF-1.7"
    await storage.delete_object(local_cfg, "knowledgeBase/test.pdf")
    assert await storage.read_object(local_cfg, "knowledgeBase/test.pdf") is None

    minio_cfg = SimpleNamespace(
        storage_dir=str(tmp_path),
        minio_endpoint="http://127.0.0.1:8088",
        minio_access_key="ak",
        minio_secret_key="sk",
        minio_bucket="demo-bucket",
        minio_region="us-east-1",
        minio_timeout_seconds=5.0,
    )
    url, headers = storage._sign_s3_headers(minio_cfg, "GET", "knowledgeBase/abc+1/2==.pdf")
    assert url == "http://127.0.0.1:8088/demo-bucket/knowledgeBase/abc%2B1/2%3D%3D.pdf"
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=ak/")


async def test_seed_data_idempotent(tmp_path: Path) -> None:
    snap = seed_data.load_snapshot()
    assert len(snap["files"]) == 1448
    assert len(snap["logs"]) == 7648
    assert len(snap["favorites"]) == 22

    added: list[object] = []

    class _FakeResult:
        def __init__(self, items: list[object]) -> None:
            self._items = items

        def scalars(self) -> list[object]:
            return self._items

        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(self._items)

    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[0, 1448]),
        execute=AsyncMock(return_value=_FakeResult([])),
        add_all=added.extend,
        flush=AsyncMock(),
    )
    inserted = await seed_data.ensure_seed_data(session, user_map={"superAdmin": "admin-uuid"})  # type: ignore[arg-type]
    assert inserted == {"files": 1448, "logs": 7648, "favorites": 22}
    assert any(getattr(row, "user_id", None) == "admin-uuid" for row in added)

    # 非 force 且库中已有数据时跳过
    skipped = await seed_data.ensure_seed_data(session)  # type: ignore[arg-type]
    assert skipped == {"files": 0, "logs": 0, "favorites": 0}

    # 快照路径不存在时使用兜底样本，且 force=True 时按主键去重
    fallback_snap = seed_data.load_snapshot(tmp_path / "missing.json.gz")
    assert len(fallback_snap["files"]) == 1
    existing_id = uuid.UUID(str(fallback_snap["files"][0]["id"]))
    session2 = SimpleNamespace(
        scalar=AsyncMock(return_value=1),
        execute=AsyncMock(side_effect=[_FakeResult([existing_id]), _FakeResult([]), _FakeResult([])]),
        add_all=lambda _rows: None,
        flush=AsyncMock(),
    )
    assert await seed_data.ensure_seed_data(
        session2,  # type: ignore[arg-type]
        force=True,
        snapshot_path=tmp_path / "missing.json.gz",
    ) == {"files": 0, "logs": 0, "favorites": 0}
