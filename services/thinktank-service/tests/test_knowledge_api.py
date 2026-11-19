"""知识库核心用例与路由端到端测试：列表、预览、收藏、下载、导出、导出未定义、上传、打标、编辑、删除与审计。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.errors import ApiError, PermissionDeniedError, VersionConflictError
from platform_common.route_audit import iter_api_routes

from app.core.database import get_db_session
from app.knowledge.api import routes as knowledge_routes
from app.knowledge.application import export_import, knowledge, knowledge_write
from app.knowledge.domain.models import KnowledgeFile, KnowledgeOpLog
from app.knowledge.domain.scopes import FULL_ACCESS, KnowledgeAccess
from app.main import app

ACTOR = Actor(id="u1", name="测试管理员")
NOW = datetime(2026, 11, 18, 8, 0, tzinfo=UTC)


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.flush = AsyncMock()
        self.commit = AsyncMock()

    def add(self, row: Any) -> None:
        self.added.append(row)

    async def delete(self, row: Any) -> None:
        self.deleted.append(row)


def _sample_file(**overrides: Any) -> KnowledgeFile:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "file_name": "专线产品培训手册-2026.pdf",
        "file_type": "产品",
        "operator_type": "电信",
        "depart_affiliation": "政企专班",
        "industry_type": "无",
        "app_scenario": "无",
        "market_category": "行客",
        "product_type": "网",
        "product_sub_type": "智算专线",
        "prov_name": "集团",
        "data_time": "2026/6",
        "uploaded_at": NOW,
        "file_suffix": "PDF",
        "file_size_bytes": 2048,
        "storage_path": "",
        "content_text": "测试文档正文摘要",
        "remark": "",
        "is_defined": True,
        "version": 1,
        "created_at": NOW,
        "created_by_id": "seed",
        "created_by_name": "系统初始化",
        "updated_at": NOW,
        "updated_by_id": "seed",
        "updated_by_name": "系统初始化",
    }
    defaults.update(overrides)
    return KnowledgeFile(**defaults)


def _hook_events(monkeypatch: pytest.MonkeyPatch, *modules: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async def _capture(_session: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    for mod in modules:
        monkeypatch.setattr(mod, "enqueue_event", _capture)
    return events


async def test_preview_favorite_download_logs_and_audit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    row = _sample_file(storage_path="knowledge/doc.pdf")
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge/doc.pdf").write_bytes(b"%PDF-1.4 sample")
    monkeypatch.setenv("THINKTANK_STORAGE_DIR", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(knowledge, "get_settings", lambda: SimpleNamespace(storage_dir=str(tmp_path)))

    op_logs: list[dict[str, Any]] = []
    events = _hook_events(monkeypatch, knowledge)
    monkeypatch.setattr(knowledge.repo, "get_by_id", AsyncMock(return_value=row))
    monkeypatch.setattr(knowledge.repo, "is_favorited", AsyncMock(return_value=False))
    monkeypatch.setattr(knowledge.repo, "set_favorite", AsyncMock(return_value=True))
    monkeypatch.setattr(
        knowledge.repo,
        "add_op_log",
        AsyncMock(side_effect=lambda _s, **kw: op_logs.append(kw)),
    )
    monkeypatch.setattr(
        knowledge.repo,
        "list_op_logs",
        AsyncMock(
            return_value=(
                [
                    KnowledgeOpLog(
                        id=uuid.uuid4(),
                        file_id=row.id,
                        actor_id="u1",
                        actor_name="测试管理员",
                        op_type="预览",
                        detail="预览资料",
                        created_at=NOW,
                    )
                ],
                1,
            )
        ),
    )

    session = _Session()
    preview_res = await knowledge.preview_knowledge(session, actor=ACTOR, access=FULL_ACCESS, file_id=row.id)  # type: ignore[arg-type]
    assert preview_res["preview"]["mode"] == "pdf"
    assert preview_res["preview"]["has_binary"] is True

    fav_res = await knowledge.toggle_favorite(session, actor=ACTOR, access=FULL_ACCESS, file_id=row.id, favorite=True)  # type: ignore[arg-type]
    assert fav_res == {"id": str(row.id), "is_favorited": True}

    dl_res = await knowledge.read_file_content(
        session,
        actor=ACTOR,
        access=FULL_ACCESS,
        file_id=row.id,
        for_download=True,  # type: ignore[arg-type]
    )
    assert dl_res.content == b"%PDF-1.4 sample"
    assert dl_res.filename == row.file_name

    # 内容预览不重复记下载日志
    inline_res = await knowledge.read_file_content(
        session,
        actor=ACTOR,
        access=FULL_ACCESS,
        file_id=row.id,
        for_download=False,  # type: ignore[arg-type]
    )
    assert inline_res.content == b"%PDF-1.4 sample"

    logs_res = await knowledge.list_logs(session, actor=ACTOR, access=FULL_ACCESS, file_id=row.id, page=1, page_size=10)  # type: ignore[arg-type]
    assert logs_res["total"] == 1
    assert [op["op_type"] for op in op_logs] == ["预览", "收藏", "下载"]
    assert [ev["event_type"] for ev in events] == [
        "thinktank.knowledge.previewed",
        "thinktank.knowledge.favorited",
        "thinktank.knowledge.downloaded",
    ]


async def test_access_denied_records_audit_and_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _sample_file(file_type="产品", industry_type="金融")
    events = _hook_events(monkeypatch, knowledge)
    monkeypatch.setattr(knowledge.repo, "get_by_id", AsyncMock(return_value=row))
    monkeypatch.setattr(knowledge.repo, "get_for_update", AsyncMock(return_value=row))

    read_only = KnowledgeAccess.from_levels(
        {"thinktank.file_type.product": "READ", "thinktank.industry_type.finance": "READ"}
    )
    session = _Session()

    # 有 READ 权限不能下载（需要 EXPORT）
    with pytest.raises(PermissionDeniedError):
        await knowledge.read_file_content(session, actor=ACTOR, access=read_only, file_id=row.id, for_download=True)  # type: ignore[arg-type]
    assert events[-1]["event_type"] == "thinktank.knowledge.access_denied"
    assert events[-1]["extra"] == {"outcome": "denied"}
    assert session.commit.await_count == 1

    # 无行业权限不能预览
    no_fin = KnowledgeAccess.from_levels({"thinktank.file_type.product": "FULL", "thinktank.industry_type.edu": "FULL"})
    with pytest.raises(PermissionDeniedError):
        await knowledge.preview_knowledge(session, actor=ACTOR, access=no_fin, file_id=row.id)  # type: ignore[arg-type]
    assert len(events) == 2

    # 不能将资料编辑移动到超出自身授权范围的行业
    with pytest.raises(PermissionDeniedError):
        await knowledge_write.update_metadata(
            session,  # type: ignore[arg-type]
            actor=ACTOR,
            access=KnowledgeAccess.from_levels(
                {"thinktank.file_type.product": "FULL", "thinktank.industry_type.finance": "FULL"}
            ),
            file_id=row.id,
            data={"version": 1, "industry_type": "军工|教育" if False else "教育"},
        )


async def test_upload_update_and_delete_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(knowledge_write, "get_settings", lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    events = _hook_events(monkeypatch, knowledge_write)
    op_logs: list[dict[str, Any]] = []
    monkeypatch.setattr(knowledge_write.repo, "add_op_log", AsyncMock(side_effect=lambda _s, **kw: op_logs.append(kw)))
    monkeypatch.setattr(knowledge_write.repo, "is_favorited", AsyncMock(return_value=False))

    session = _Session()
    created = await knowledge_write.upload_knowledge_file(
        session,  # type: ignore[arg-type]
        actor=ACTOR,
        access=FULL_ACCESS,
        filename="行业方案.pdf",
        content=b"%PDF-1.7",
        metadata={"file_type": "产品", "industry_type": "教育", "market_category": "行客"},
    )
    assert created["file_name"] == "行业方案.pdf"
    assert created["is_defined"] is True
    assert events[-1]["event_type"] == "thinktank.knowledge.created"

    # 不支持扩展名拒收
    with pytest.raises(ApiError, match="仅支持"):
        await knowledge_write.upload_knowledge_file(
            session,  # type: ignore[arg-type]
            actor=ACTOR,
            access=FULL_ACCESS,
            filename="script.exe",
            content=b"bad",
            metadata={},
        )

    # 乐观锁冲突与枚举校验
    stored_row: KnowledgeFile = session.added[0]
    monkeypatch.setattr(knowledge_write.repo, "get_for_update", AsyncMock(return_value=stored_row))
    with pytest.raises(VersionConflictError):
        await knowledge_write.update_metadata(
            session,
            actor=ACTOR,
            access=FULL_ACCESS,
            file_id=stored_row.id,
            data={"version": 9},  # type: ignore[arg-type]
        )
    with pytest.raises(ApiError, match="不支持的运营商类型"):
        await knowledge_write.update_metadata(
            session,  # type: ignore[arg-type]
            actor=ACTOR,
            access=FULL_ACCESS,
            file_id=stored_row.id,
            data={"version": 1, "operator_type": "非法运营商"},
        )

    updated = await knowledge_write.update_metadata(
        session,  # type: ignore[arg-type]
        actor=ACTOR,
        access=FULL_ACCESS,
        file_id=stored_row.id,
        data={"version": 1, "industry_type": "中小|教育", "product_type": "云|网"},
    )
    assert updated["version"] == 2
    assert updated["industry_type"] == "中小|教育"
    assert events[-1]["event_type"] == "thinktank.knowledge.updated"

    deleted = await knowledge_write.delete_knowledge_file(
        session,
        actor=ACTOR,
        access=FULL_ACCESS,
        file_id=stored_row.id,  # type: ignore[arg-type]
    )
    assert deleted == {"deleted": True}
    assert events[-1]["event_type"] == "thinktank.knowledge.deleted"


async def test_export_undefined_and_upload_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    undef_row = _sample_file(file_name="未分类调研.pdf", file_type="", is_defined=False)
    events = _hook_events(monkeypatch, export_import)
    monkeypatch.setattr(export_import.repo, "count_undefined", AsyncMock(return_value=1))
    monkeypatch.setattr(export_import.repo, "list_undefined", AsyncMock(return_value=[undef_row]))
    monkeypatch.setattr(export_import.repo, "count_filtered", AsyncMock(return_value=1))
    monkeypatch.setattr(export_import.repo, "list_filtered", AsyncMock(return_value=[undef_row]))
    monkeypatch.setattr(export_import.repo, "get_for_update", AsyncMock(side_effect=[undef_row, None]))
    monkeypatch.setattr(export_import.repo, "get_by_file_name", AsyncMock(return_value=None))
    monkeypatch.setattr(export_import.repo, "add_op_log", AsyncMock())

    session = _Session()
    # 导出列表 + 导出未定义数据均写入对应审计事件
    excel_all = await export_import.export_filtered_excel(
        session,
        actor=ACTOR,
        access=FULL_ACCESS,
        filters={"file_type": ["产品"]},  # type: ignore[arg-type]
    )
    assert len(excel_all) > 100
    assert events[-1]["event_type"] == "thinktank.knowledge.exported"

    excel_undef = await export_import.export_undefined_excel(session, actor=ACTOR, access=FULL_ACCESS)  # type: ignore[arg-type]
    assert len(excel_undef) > 100
    assert events[-1]["event_type"] == "thinktank.knowledge.export_undefined"

    # 无未定义导出权限时拒绝
    no_undef = KnowledgeAccess.from_levels(
        {"thinktank.file_type.product": "EXPORT", "thinktank.industry_type.none": "EXPORT"}
    )
    with pytest.raises(PermissionDeniedError):
        await export_import.export_undefined_excel(session, actor=ACTOR, access=no_undef)  # type: ignore[arg-type]

    # 上传知识标签：第1行合法更新，第2行非法运营商类型写入跳过明细
    missing_id = uuid.uuid4()
    if str(missing_id).lower() < str(undef_row.id).lower():
        undef_row.id, missing_id = missing_id, undef_row.id
    parsed_rows = [
        {
            "id": str(undef_row.id),
            "file_name": undef_row.file_name,
            "file_type": "产品",
            "operator_type": "电信",
            "industry_type": "教育",
        },
        {
            "id": str(missing_id),
            "file_name": "不存在文件.pdf",
            "file_type": "产品",
            "operator_type": "非法",
            "industry_type": "教育",
        },
    ]
    monkeypatch.setattr(export_import, "parse_sheet_async", AsyncMock(return_value=parsed_rows))

    result = await export_import.upload_knowledge_tags(session, actor=ACTOR, access=FULL_ACCESS, content=b"xlsx")  # type: ignore[arg-type]
    assert result["total"] == 2
    assert result["updated"] == 1
    assert result["skipped"] == 1
    assert result["skipped_file"] is not None
    assert undef_row.file_type == "产品"
    assert undef_row.is_defined is True
    assert events[-1]["event_type"] == "thinktank.knowledge.upload_tags"

    # 重复提交无变化的行不再虚增 updated 计数
    monkeypatch.setattr(export_import.repo, "get_for_update", AsyncMock(return_value=undef_row))
    monkeypatch.setattr(export_import, "parse_sheet_async", AsyncMock(return_value=[parsed_rows[0]]))
    unchanged_res = await export_import.upload_knowledge_tags(session, actor=ACTOR, access=FULL_ACCESS, content=b"xlsx")  # type: ignore[arg-type]
    assert unchanged_res["updated"] == 0
    assert unchanged_res["skipped"] == 0

    # 导出未定义数据超过上限返回 422
    monkeypatch.setattr(export_import.repo, "count_undefined", AsyncMock(return_value=200_000))
    with pytest.raises(ApiError, match="超过上限"):
        await export_import.export_undefined_excel(session, actor=ACTOR, access=FULL_ACCESS)  # type: ignore[arg-type]

    # 原范围与目标范围无权时的区分提示
    only_edu = KnowledgeAccess.from_levels(
        {"thinktank.file_type.product": "FULL", "thinktank.industry_type.edu": "FULL"}
    )
    fin_row = _sample_file(file_type="产品", industry_type="金融")
    assert "原范围" in (export_import._check_tag_row_permission(only_edu, fin_row, "产品", "教育") or "")
    assert "目标范围" in (export_import._check_tag_row_permission(only_edu, undef_row, "产品", "金融") or "")


async def test_storage_unavailable_and_upload_rollback_cleanup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    row = _sample_file(file_type="产品", industry_type="金融", storage_path="knowledgeBase/sample.pdf")
    monkeypatch.setattr(knowledge.repo, "get_by_id", AsyncMock(return_value=row))
    monkeypatch.setattr(
        knowledge.storage,
        "read_object",
        AsyncMock(side_effect=knowledge.storage.StorageUnavailableError("timeout")),
    )
    session = _Session()
    with pytest.raises(ApiError, match="文件存储服务暂不可用") as exc_info:
        await knowledge.read_file_content(session, actor=ACTOR, access=FULL_ACCESS, file_id=row.id, for_download=True)  # type: ignore[arg-type]
    assert exc_info.value.http_status == 503

    # 上传对象存储失败返回 503
    monkeypatch.setattr(knowledge_write, "get_settings", lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    monkeypatch.setattr(
        knowledge_write.storage,
        "save_object",
        AsyncMock(side_effect=knowledge_write.storage.StorageUnavailableError("down")),
    )
    with pytest.raises(ApiError, match="上传失败") as up_exc:
        await knowledge_write.upload_knowledge_file(
            session,  # type: ignore[arg-type]
            actor=ACTOR,
            access=FULL_ACCESS,
            filename="方案.pdf",
            content=b"%PDF",
            metadata={"file_type": "产品", "industry_type": "教育"},
        )
    assert up_exc.value.http_status == 503

    # 写库失败触发已上传对象的补偿清理
    monkeypatch.setattr(knowledge_write.storage, "save_object", AsyncMock())
    cleanup_mock = AsyncMock()
    monkeypatch.setattr(knowledge_write.storage, "delete_object", cleanup_mock)
    bad_session = _Session()
    bad_session.flush = AsyncMock(side_effect=RuntimeError("db_boom"))
    with pytest.raises(RuntimeError, match="db_boom"):
        await knowledge_write.upload_knowledge_file(
            bad_session,  # type: ignore[arg-type]
            actor=ACTOR,
            access=FULL_ACCESS,
            filename="方案.pdf",
            content=b"%PDF",
            metadata={"file_type": "产品", "industry_type": "教育"},
        )
    assert cleanup_mock.await_count == 1

    # 删除记录先提交数据库再删对象，对象存储异常不阻断删除
    managed_row = _sample_file(file_type="产品", industry_type="教育")
    managed_row.storage_path = knowledge_write.storage.new_object_key(managed_row.id, "pdf")
    monkeypatch.setattr(knowledge_write.repo, "get_for_update", AsyncMock(return_value=managed_row))
    _hook_events(monkeypatch, knowledge_write)
    monkeypatch.setattr(
        knowledge_write.storage,
        "delete_object",
        AsyncMock(side_effect=knowledge_write.storage.StorageUnavailableError("minio_down")),
    )
    del_session = _Session()
    assert await knowledge_write.delete_knowledge_file(
        del_session, actor=ACTOR, access=FULL_ACCESS, file_id=managed_row.id
    ) == {  # type: ignore[arg-type]
        "deleted": True
    }
    assert del_session.commit.await_count == 1

    # 同步码表省枚举（配置与未配置兜底）
    from app.common import codebook_client

    codebook_client.clear_province_cache()
    assert await codebook_client.get_provinces(
        SimpleNamespace(codebook_base_url="", codebook_service_secret="", codebook_timeout_seconds=1.0),
        ("集团", "北京市"),
    ) == ["集团", "北京市"]

    merged = codebook_client._merge_provinces(["上海市", "浙江省", "集团"], ("集团",))
    assert merged == ["集团", "上海市", "浙江省"]


def test_http_routes_wire_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _db():  # type: ignore[no-untyped-def]
        yield None

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[knowledge_routes.get_knowledge_access] = lambda: FULL_ACCESS
    for route in iter_api_routes(app):
        for dep in route.dependant.dependencies:
            if dep.name in {"actor", "_"}:
                app.dependency_overrides[dep.call] = lambda: ACTOR

    row_id = uuid.uuid4()
    monkeypatch.setattr(
        knowledge_routes.service,
        "list_knowledge",
        AsyncMock(return_value={"items": [], "total": 0, "page": 1, "page_size": 20}),
    )
    monkeypatch.setattr(
        knowledge_routes.service,
        "get_options",
        AsyncMock(return_value={"file_type": ["产品"], "industry_type": ["教育"]}),
    )
    monkeypatch.setattr(
        knowledge_routes.service,
        "toggle_favorite",
        AsyncMock(return_value={"id": str(row_id), "is_favorited": True}),
    )
    monkeypatch.setattr(
        knowledge_routes.service,
        "read_file_content",
        AsyncMock(
            return_value=knowledge.FileContentResult(content=b"hello", filename="测试文件.txt", media_type="text/plain")
        ),
    )

    try:
        client = TestClient(app)
        assert client.get("/api/v1/thinktank/knowledge").status_code == 200
        assert client.get("/api/v1/thinktank/knowledge/access").status_code == 200
        assert client.get("/api/v1/thinktank/knowledge/options").status_code == 200
        assert client.post(f"/api/v1/thinktank/knowledge/{row_id}/favorite").json()["data"]["is_favorited"] is True
        dl = client.get(f"/api/v1/thinktank/knowledge/{row_id}/download")
        assert dl.status_code == 200
        assert "attachment" in dl.headers["content-disposition"]
    finally:
        app.dependency_overrides.clear()
