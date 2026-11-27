"""报告库与方案库端到端单测：仓储查询、上传/编辑/删除、导出/未定义/批量标签、预览/Range/下载/收藏/日志、路由与安全检查。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.errors import ApiError, NotFoundError, VersionConflictError
from platform_common.route_audit import iter_api_routes
from sqlalchemy.dialects import postgresql

from app.common.preview import FileStreamResult
from app.common.security import LibraryAccess, get_library_access
from app.core import preview_cache
from app.core.database import get_db_session
from app.library.api import routes as library_routes
from app.library.application import export_import, library_read, library_write
from app.library.application.library_write import UploadPayload
from app.library.domain.models import ProposalFile, ProposalOpLog, ReportFile, ReportOpLog
from app.library.domain.specs import PROPOSAL_SPEC, REPORT_SPEC, LibrarySpec
from app.library.repositories import library as repo
from app.main import app
from tests.helpers import no_pdf_tools, preview_settings

ACTOR = Actor(id="u1", name="测试管理员")
NOW = datetime(2026, 11, 27, 8, 0, tzinfo=UTC)
FULL_LIB_ACCESS = LibraryAccess(level="FULL", allow_download=True)
READ_LIB_ACCESS = LibraryAccess(level="READ")


def _sql_text(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


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


class _FakeResult:
    def __init__(self, rows: list[Any] | None = None, scalar_val: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar_val

    def scalars(self) -> list[Any]:
        return self._rows

    def scalar_one_or_none(self) -> Any:
        return self._scalar


class _RecordingSession:
    def __init__(self, results: list[Any] | None = None, scalars: list[Any] | None = None) -> None:
        self.stmts: list[Any] = []
        self.added: list[Any] = []
        self._results = list(results or [])
        self._scalars = list(scalars or [])
        self.get = AsyncMock(return_value=None)
        self.flush = AsyncMock()

    def add(self, row: Any) -> None:
        self.added.append(row)

    async def execute(self, stmt: Any) -> _FakeResult:
        self.stmts.append(stmt)
        return self._results.pop(0) if self._results else _FakeResult()

    async def scalar(self, stmt: Any) -> Any:
        self.stmts.append(stmt)
        return self._scalars.pop(0) if self._scalars else 0


def _sample_report(**overrides: Any) -> ReportFile:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "report_name": "2026智算市场洞察报告",
        "project_name": "智算专项",
        "customer_name": "某省政务云",
        "report_type": "行业研究",
        "industry_tags": "党政|教育",
        "region_tag": "广东省",
        "delivery_dept": "政企部",
        "participants": "张三、李四",
        "is_temp_support": "否",
        "delivery_date": "2026-11-20",
        "summary": "核心结论摘要",
        "keywords": "智算,政务云,大模型",
        "data_sources": "公开年报",
        "uploaded_at": NOW,
        "file_suffix": "PDF",
        "file_size_bytes": 4096,
        "storage_path": "",
        "content_text": "报告全文摘要",
        "remark": "",
        "is_defined": True,
        "version": 1,
        "created_at": NOW,
        "created_by_id": "u1",
        "created_by_name": "测试管理员",
        "updated_at": NOW,
        "updated_by_id": "u1",
        "updated_by_name": "测试管理员",
    }
    defaults.update(overrides)
    return ReportFile(**defaults)


def _sample_proposal(**overrides: Any) -> ProposalFile:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "proposal_name": "智慧交通云网融合建设方案",
        "customer_name": "省交通厅",
        "proposal_type": "售前方案",
        "industry_tags": "交通物流",
        "region_tag": "江苏省",
        "opportunity_source": "政企大客",
        "bidding_method": "公开招标",
        "bid_deadline": "2026-12-15",
        "owner_dept": "交通物流行业事业部",
        "owner_name": "王五",
        "quote_amount": "1200",
        "result_status": "中标",
        "win_amount": "1150",
        "selling_points": "端到端低时延专网+AI视频分析",
        "uploaded_at": NOW,
        "file_suffix": "PPT",
        "file_size_bytes": 8192,
        "storage_path": "",
        "content_text": "",
        "remark": "",
        "is_defined": True,
        "version": 1,
        "created_at": NOW,
        "created_by_id": "u1",
        "created_by_name": "测试管理员",
        "updated_at": NOW,
        "updated_by_id": "u1",
        "updated_by_name": "测试管理员",
    }
    defaults.update(overrides)
    return ProposalFile(**defaults)


def _hook_events(monkeypatch: pytest.MonkeyPatch, *modules: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async def _capture(_session: Any, **kwargs: Any) -> None:
        events.append(kwargs)

    for mod in modules:
        monkeypatch.setattr(mod, "enqueue_event", _capture)
    return events


def test_library_repo_filter_sql_builders() -> None:
    r_conds = repo.build_conditions(
        REPORT_SPEC,
        {
            "report_name": ["洞察"],
            "report_type": ["行业研究"],
            "industry_tags": ["党政"],
            "region_tag": ["广东省"],
            "delivery_dept": ["政企部"],
            "is_temp_support": ["否"],
            "tag_status": ["defined"],
            "favorite_only": ["true"],
        },
        user_id="u1",
    )
    r_sql = " AND ".join(_sql_text(c) for c in r_conds)
    assert "thinktank_report_files.report_name ILIKE" in r_sql
    assert "thinktank_report_files.is_defined IS true" in r_sql
    assert "thinktank_report_favorites.user_id" in r_sql

    p_conds = repo.build_conditions(
        PROPOSAL_SPEC,
        {"proposal_name": ["交通"], "result_status": ["中标"], "tag_status": ["未定义"], "favorite_only": ["仅看收藏"]},
        user_id="u1",
    )
    p_sql = " AND ".join(_sql_text(c) for c in p_conds)
    assert "thinktank_proposal_files.is_defined IS false" in p_sql
    assert "thinktank_proposal_favorites.user_id" in p_sql

    with pytest.raises(KeyError):
        repo.build_conditions(REPORT_SPEC, {"bad_field": ["x"]}, user_id="u1")


async def test_library_repo_crud_and_options(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _sample_report()
    log_row = ReportOpLog(
        id=uuid.uuid4(),
        file_id=row.id,
        actor_id="u1",
        actor_name="测试",
        op_type="预览",
        detail="d",
        created_at=NOW,
    )
    sess = _RecordingSession(
        results=[
            _FakeResult([row]),
            _FakeResult([row]),
            _FakeResult([row]),
            _FakeResult(scalar_val=row),
            _FakeResult([row.id]),
            _FakeResult([log_row]),
        ],
        scalars=[1, 1, 1, None, row.id, row.id, 1],
    )
    sess.get = AsyncMock(return_value=row)  # type: ignore[method-assign]

    items, total = await repo.list_items(sess, REPORT_SPEC, filters={}, user_id="u1", page=1, page_size=20)  # type: ignore[arg-type]
    assert len(items) == 1 and total == 1
    assert "content_text" not in _sql_text(sess.stmts[1])
    assert await repo.count_filtered(sess, REPORT_SPEC, {}, user_id="u1") == 1  # type: ignore[arg-type]
    assert len(await repo.list_filtered(sess, REPORT_SPEC, {}, user_id="u1")) == 1  # type: ignore[arg-type]
    assert "content_text" not in _sql_text(sess.stmts[3]) and "remark" not in _sql_text(sess.stmts[3])
    assert await repo.count_undefined(sess, REPORT_SPEC) == 1  # type: ignore[arg-type]
    assert len(await repo.list_undefined(sess, REPORT_SPEC)) == 1  # type: ignore[arg-type]
    assert await repo.get_by_id(sess, REPORT_SPEC, row.id) is row  # type: ignore[arg-type]
    assert await repo.get_for_update(sess, REPORT_SPEC, row.id) is row  # type: ignore[arg-type]
    assert await repo.get_by_title(sess, REPORT_SPEC, row.report_name) is row  # type: ignore[arg-type]
    assert await repo.favorite_ids_for_user(sess, REPORT_SPEC, user_id="u1", file_ids=[]) == set()  # type: ignore[arg-type]
    assert await repo.favorite_ids_for_user(sess, REPORT_SPEC, user_id="u1", file_ids=[row.id]) == {row.id}  # type: ignore[arg-type]
    assert await repo.is_favorited(sess, REPORT_SPEC, user_id="u1", file_id=row.id) is False  # type: ignore[arg-type]
    assert await repo.set_favorite(sess, REPORT_SPEC, user_id="u1", file_id=row.id, favorite=True) is True  # type: ignore[arg-type]
    assert await repo.set_favorite(sess, REPORT_SPEC, user_id="u1", file_id=row.id, favorite=False) is True  # type: ignore[arg-type]
    await repo.add_op_log(sess, REPORT_SPEC, file_id=row.id, actor=ACTOR, op_type="预览")  # type: ignore[arg-type]
    logs, log_total = await repo.list_op_logs(sess, REPORT_SPEC, file_id=row.id, page=1, page_size=10)  # type: ignore[arg-type]
    assert len(logs) == 1 and log_total == 1


async def test_library_options_merge_codebooks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        repo,
        "preview_options",
        AsyncMock(
            return_value={
                "industry_tags": {"items": ["党政|医疗"], "truncated": False},
                "region_tag": {"items": ["浙江省"], "truncated": False},
                "delivery_dept": {"items": ["自有部门"], "truncated": False},
                "owner_dept": {"items": ["方案团队"], "truncated": False},
                "is_temp_support": {"items": [], "truncated": False},
                "result_status": {"items": ["放弃"], "truncated": False},
            }
        ),
    )
    dicts = {"industries": ["党政", "教育"], "provinces": ["集团", "北京市"], "departments": ["政企部"]}
    monkeypatch.setattr(library_read, "get_thinktank_dicts", AsyncMock(return_value=dicts))

    r_opts = (await library_read.get_options(AsyncMock(), REPORT_SPEC))["options"]
    assert r_opts["industry_tags"]["items"] == ["党政", "教育", "医疗"]
    assert r_opts["region_tag"]["items"] == ["集团", "北京市", "浙江省"]
    assert r_opts["delivery_dept"]["items"] == ["政企部", "自有部门"]
    assert r_opts["is_temp_support"]["items"] == ["是", "否"]
    assert r_opts["tag_status"]["items"] == ["已定义", "未定义"]
    assert r_opts["favorite_only"]["items"] == ["仅看收藏"]

    p_opts = (await library_read.get_options(AsyncMock(), PROPOSAL_SPEC))["options"]
    assert p_opts["owner_dept"]["items"] == ["政企部", "方案团队"]
    assert p_opts["result_status"]["items"] == ["中标", "未中标", "待定", "流标", "放弃"]

    monkeypatch.setattr(repo, "search_options", AsyncMock(return_value=["教育|医疗"]))
    assert await library_read.search_options(AsyncMock(), REPORT_SPEC, field="industry_tags", keyword="教") == ["教育"]
    assert await library_read.search_options(AsyncMock(), PROPOSAL_SPEC, field="tag_status", keyword="已") == ["已定义"]
    with pytest.raises(KeyError):
        await library_read.search_options(AsyncMock(), PROPOSAL_SPEC, field="no_such", keyword=None)


@pytest.mark.parametrize("spec", [REPORT_SPEC, PROPOSAL_SPEC])
async def test_library_upload_and_update(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, spec: LibrarySpec) -> None:
    monkeypatch.setattr(library_write, "get_settings", lambda: preview_settings(tmp_path))
    events = _hook_events(monkeypatch, library_write)
    monkeypatch.setattr(library_write.repo, "add_op_log", AsyncMock())
    monkeypatch.setattr(library_write.repo, "is_favorited", AsyncMock(return_value=False))

    session = _Session()
    meta = {
        spec.title_field: f"年度重点{spec.item_noun}",
        spec.category_field: "专题类",
        "industry_tags": "党政 | 教育",
    }
    created = await library_write.upload_file(
        session,  # type: ignore[arg-type]
        spec,
        actor=ACTOR,
        access=FULL_LIB_ACCESS,
        payload=UploadPayload(filename="raw.pdf", content=b"%PDF-1.7 body", metadata=meta),
    )
    assert created[spec.title_field] == f"年度重点{spec.item_noun}"
    assert created["industry_tags"] == "党政|教育"
    assert created["is_defined"] is True
    assert created["can_export"] is True and created["can_edit"] is True

    row = session.added[0]
    assert row.storage_path.startswith(f"{spec.storage_prefix}/")
    assert events[-1]["event_type"] == f"{spec.event_prefix}.created"

    with pytest.raises(ApiError, match="仅支持"):
        await library_write.upload_file(
            session,  # type: ignore[arg-type]
            spec,
            actor=ACTOR,
            access=FULL_LIB_ACCESS,
            payload=UploadPayload(filename="evil.exe", content=b"x", metadata={}),
        )

    monkeypatch.setattr(library_write.repo, "get_for_update", AsyncMock(return_value=row))
    with pytest.raises(VersionConflictError):
        await library_write.update_metadata(
            session,  # type: ignore[arg-type]
            spec,
            actor=ACTOR,
            access=FULL_LIB_ACCESS,
            file_id=row.id,
            data={"version": 99, "remark": "conflict"},
        )
    with pytest.raises(ApiError, match="不能为空"):
        await library_write.update_metadata(
            session,  # type: ignore[arg-type]
            spec,
            actor=ACTOR,
            access=FULL_LIB_ACCESS,
            file_id=row.id,
            data={"version": 1, spec.title_field: "  "},
        )
    if spec is REPORT_SPEC:
        with pytest.raises(ApiError, match="是否临时支撑"):
            await library_write.update_metadata(
                session,  # type: ignore[arg-type]
                spec,
                actor=ACTOR,
                access=FULL_LIB_ACCESS,
                file_id=row.id,
                data={"version": 1, "is_temp_support": "也许"},
            )

    updated = await library_write.update_metadata(
        session,  # type: ignore[arg-type]
        spec,
        actor=ACTOR,
        access=FULL_LIB_ACCESS,
        file_id=row.id,
        data={"version": 1, "remark": "已复核"},
    )
    assert updated["version"] == 2 and updated["remark"] == "已复核"


@pytest.mark.parametrize("spec", [REPORT_SPEC, PROPOSAL_SPEC])
async def test_library_preview_download_logs_and_delete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, spec: LibrarySpec
) -> None:
    monkeypatch.setattr(library_write, "get_settings", lambda: preview_settings(tmp_path))
    monkeypatch.setattr(library_read, "get_settings", lambda: preview_settings(tmp_path))
    no_pdf_tools(monkeypatch)
    events = _hook_events(monkeypatch, library_write, library_read)
    monkeypatch.setattr(library_read.repo, "add_op_log", AsyncMock())
    monkeypatch.setattr(library_read.repo, "is_favorited", AsyncMock(return_value=True))
    monkeypatch.setattr(library_read.repo, "set_favorite", AsyncMock(return_value=True))

    row = _sample_report() if spec is REPORT_SPEC else _sample_proposal()
    rel = f"{spec.storage_prefix}/{row.id.hex}.pdf"
    row.storage_path = rel
    row.file_suffix = "PDF"
    row.file_size_bytes = 13
    (tmp_path / spec.storage_prefix).mkdir(parents=True, exist_ok=True)
    (tmp_path / rel).write_bytes(b"%PDF-1.7 body")

    monkeypatch.setattr(library_read.repo, "get_by_id", AsyncMock(return_value=row))
    monkeypatch.setattr(library_read.repo, "list_items", AsyncMock(return_value=([row], 1)))
    monkeypatch.setattr(library_read.repo, "favorite_ids_for_user", AsyncMock(return_value={row.id}))
    monkeypatch.setattr(library_write.repo, "get_for_update", AsyncMock(return_value=row))

    session = _Session()
    listed = await library_read.list_library(
        session,  # type: ignore[arg-type]
        spec,
        actor=ACTOR,
        access=READ_LIB_ACCESS,
        filters={},
        pagination=(1, 20),
    )
    assert listed["total"] == 1 and listed["items"][0]["is_favorited"] is True
    detail = await library_read.get_detail(
        session,  # type: ignore[arg-type]
        spec,
        actor=ACTOR,
        access=READ_LIB_ACCESS,
        file_id=row.id,
    )
    assert detail["can_download"] is False and detail["can_export"] is False and detail["can_edit"] is False

    dl_only_detail = await library_read.get_detail(
        session,  # type: ignore[arg-type]
        spec,
        actor=ACTOR,
        access=LibraryAccess(level="READ", allow_download=True),
        file_id=row.id,
    )
    assert dl_only_detail["can_download"] is True and dl_only_detail["can_export"] is False

    preview_res = await library_read.preview_item(
        session,  # type: ignore[arg-type]
        spec,
        actor=ACTOR,
        access=READ_LIB_ACCESS,
        file_id=row.id,
    )
    assert preview_res["preview"]["mode"] == "pdf"

    inline = await library_read.stream_file_content(
        session,  # type: ignore[arg-type]
        spec,
        actor=ACTOR,
        file_id=row.id,
        for_download=False,
    )
    assert inline.ranged is True and inline.etag
    assert b"".join([c async for c in inline.stream]) == b"%PDF-1.7 body"
    not_mod = await library_read.stream_file_content(
        session,  # type: ignore[arg-type]
        spec,
        actor=ACTOR,
        file_id=row.id,
        for_download=False,
        if_none_match=inline.etag,
    )
    assert not_mod.not_modified is True

    dl = await library_read.stream_file_content(
        session,  # type: ignore[arg-type]
        spec,
        actor=ACTOR,
        file_id=row.id,
        for_download=True,
    )
    assert dl.filename.endswith(".pdf")
    assert b"".join([c async for c in dl.stream]) == b"%PDF-1.7 body"

    assert await library_read.toggle_favorite(
        session,  # type: ignore[arg-type]
        spec,
        actor=ACTOR,
        file_id=row.id,
        favorite=True,
    ) == {"id": str(row.id), "is_favorited": True}

    log_cls = ReportOpLog if spec is REPORT_SPEC else ProposalOpLog
    log_item = log_cls(
        id=uuid.uuid4(),
        file_id=row.id,
        actor_id="u1",
        actor_name="测试",
        op_type="上传",
        detail="ok",
        created_at=NOW,
    )
    monkeypatch.setattr(library_read.repo, "list_op_logs", AsyncMock(return_value=([log_item], 1)))
    assert (await library_read.list_logs(session, spec, file_id=row.id, page=1, page_size=10))["total"] == 1  # type: ignore[arg-type]

    cache_dir = tmp_path / "preview_cache"
    assert any(cache_dir.glob("*.pdf"))
    assert await library_write.delete_file(session, spec, actor=ACTOR, file_id=row.id) == {"deleted": True}  # type: ignore[arg-type]
    assert not list(cache_dir.glob("*.pdf"))
    assert events[-1]["event_type"] == f"{spec.event_prefix}.deleted"

    monkeypatch.setattr(library_read.repo, "get_by_id", AsyncMock(return_value=None))
    with pytest.raises(NotFoundError):
        await library_read.get_detail(
            session,  # type: ignore[arg-type]
            spec,
            actor=ACTOR,
            access=FULL_LIB_ACCESS,
            file_id=uuid.uuid4(),
        )


async def test_library_export_undefined_upload_tags_and_warmup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = _sample_report(report_type="", industry_tags="", is_defined=False)
    proposal = _sample_proposal(proposal_type="", industry_tags="", is_defined=False)
    events = _hook_events(monkeypatch, export_import)
    session = _Session()

    for spec, row in ((REPORT_SPEC, report), (PROPOSAL_SPEC, proposal)):
        monkeypatch.setattr(export_import.repo, "count_filtered", AsyncMock(return_value=1))
        monkeypatch.setattr(export_import.repo, "list_filtered", AsyncMock(return_value=[row]))
        monkeypatch.setattr(export_import.repo, "count_undefined", AsyncMock(return_value=1))
        monkeypatch.setattr(export_import.repo, "list_undefined", AsyncMock(return_value=[row]))
        monkeypatch.setattr(export_import.repo, "add_op_log", AsyncMock())

        excel_all = await export_import.export_filtered_excel(session, spec, actor=ACTOR, filters={})  # type: ignore[arg-type]
        assert len(excel_all) > 100
        excel_undef = await export_import.export_undefined_excel(session, spec, actor=ACTOR)  # type: ignore[arg-type]
        assert len(excel_undef) > 100

        missing_id = uuid.uuid4()
        if str(missing_id).lower() < str(row.id).lower():
            row.id, missing_id = missing_id, row.id
        monkeypatch.setattr(export_import.repo, "get_for_update", AsyncMock(side_effect=[row, None]))
        monkeypatch.setattr(export_import.repo, "get_by_title", AsyncMock(return_value=None))
        monkeypatch.setattr(
            export_import,
            "parse_sheet_async",
            AsyncMock(
                return_value=[
                    {"id": str(row.id), spec.category_field: "标杆类", "industry_tags": "金融|教育"},
                    {"id": str(missing_id), spec.title_field: "不存在"},
                ]
            ),
        )
        res = await export_import.upload_tags(session, spec, actor=ACTOR, content=b"xlsx")  # type: ignore[arg-type]
        assert res["updated"] == 1 and res["skipped"] == 1 and res["skipped_file"] is not None
        assert row.is_defined is True and row.industry_tags == "金融|教育"

    assert any(ev["event_type"] == "thinktank.reports.upload_tags" for ev in events)
    assert any(ev["event_type"] == "thinktank.proposals.upload_tags" for ev in events)

    tasks = BackgroundTasks()
    assert library_read.schedule_upload_warmup(
        tasks, SimpleNamespace(preview_warmup_on_upload=True), "reports", str(report.id)
    )
    assert not library_read.schedule_upload_warmup(
        tasks, SimpleNamespace(preview_warmup_on_upload=False), "reports", str(report.id)
    )
    pdf_path = tmp_path / "reports" / "w.pdf"
    await asyncio.to_thread(pdf_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(pdf_path.write_bytes, b"%PDF-1.7")
    warm_row = _sample_report(storage_path="reports/w.pdf", file_size_bytes=8)
    monkeypatch.setattr(library_read, "get_settings", lambda: preview_settings(tmp_path))
    no_pdf_tools(monkeypatch)
    monkeypatch.setattr(library_read.repo, "get_by_id", AsyncMock(return_value=warm_row))

    @asynccontextmanager
    async def _sf() -> AsyncIterator[None]:
        yield None

    await library_read.warm_preview("reports", warm_row.id, session_factory=_sf)  # type: ignore[arg-type]
    key = preview_cache.cache_key_for(str(warm_row.id), warm_row.storage_path, warm_row.file_size_bytes, "preview-v2")
    assert preview_cache.pdf_path(str(tmp_path / "preview_cache"), key).is_file()


def _install_library_route_mocks(monkeypatch: pytest.MonkeyPatch, fid: uuid.UUID) -> None:
    async def _db():  # type: ignore[no-untyped-def]
        yield None

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_library_access] = lambda: FULL_LIB_ACCESS
    for route in iter_api_routes(app):
        for dep in route.dependant.dependencies:
            if dep.name in {"actor", "_"}:
                app.dependency_overrides[dep.call] = lambda: ACTOR

    async def _chunks() -> AsyncIterator[bytes]:
        yield b"%PDF"

    monkeypatch.setattr(
        library_routes.read_service,
        "list_library",
        AsyncMock(return_value={"items": [], "total": 0, "page": 1, "page_size": 20}),
    )
    monkeypatch.setattr(library_routes.read_service, "get_options", AsyncMock(return_value={"options": {}}))
    monkeypatch.setattr(library_routes.read_service, "search_options", AsyncMock(return_value=["党政"]))
    monkeypatch.setattr(library_routes.export_import, "export_filtered_excel", AsyncMock(return_value=b"xlsx"))
    monkeypatch.setattr(library_routes.export_import, "export_undefined_excel", AsyncMock(return_value=b"undef"))
    monkeypatch.setattr(library_routes.write_service, "upload_file", AsyncMock(return_value={"id": str(fid)}))
    monkeypatch.setattr(library_routes.read_service, "schedule_upload_warmup", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        library_routes.export_import,
        "upload_tags",
        AsyncMock(
            return_value={
                "total": 1,
                "inserted": 0,
                "updated": 1,
                "skipped": 0,
                "rejected": False,
                "skipped_file": None,
            }
        ),
    )
    monkeypatch.setattr(library_routes.read_service, "get_detail", AsyncMock(return_value={"id": str(fid)}))
    monkeypatch.setattr(
        library_routes.read_service,
        "preview_item",
        AsyncMock(return_value={"item": {"id": str(fid)}, "preview": {"mode": "pdf"}}),
    )
    monkeypatch.setattr(
        library_routes.read_service,
        "stream_file_content",
        AsyncMock(
            side_effect=lambda *_a, **_kw: FileStreamResult(
                stream=_chunks(), filename="demo.pdf", media_type="application/pdf", content_length=4
            )
        ),
    )
    monkeypatch.setattr(
        library_routes.read_service,
        "toggle_favorite",
        AsyncMock(return_value={"id": str(fid), "is_favorited": True}),
    )
    monkeypatch.setattr(
        library_routes.read_service,
        "list_logs",
        AsyncMock(return_value={"items": [], "total": 0, "page": 1, "page_size": 10}),
    )
    monkeypatch.setattr(
        library_routes.write_service,
        "update_metadata",
        AsyncMock(return_value={"id": str(fid), "version": 2}),
    )
    monkeypatch.setattr(library_routes.write_service, "delete_file", AsyncMock(return_value={"deleted": True}))


@pytest.mark.parametrize("slug", ["reports", "proposals"])
def test_library_http_routes_end_to_end(monkeypatch: pytest.MonkeyPatch, slug: str) -> None:
    unauth = TestClient(app)
    assert unauth.post(f"/api/v1/thinktank/{slug}/upload", files={"file": ("a.pdf", b"%PDF")}).status_code == 401
    assert unauth.post(f"/api/v1/thinktank/{slug}/upload-tags", files={"file": ("t.xlsx", b"PK")}).status_code == 401

    fid = uuid.uuid4()
    _install_library_route_mocks(monkeypatch, fid)
    try:
        client = TestClient(app, headers={"Authorization": "Bearer test"})
        base = f"/api/v1/thinktank/{slug}"
        assert client.get(base).status_code == 200
        assert client.get(f"{base}/options").status_code == 200
        assert client.get(f"{base}/options/search", params={"field": "industry_tags", "q": "党"}).status_code == 200
        assert client.get(f"{base}/export").status_code == 200
        assert client.get(f"{base}/export-undefined").status_code == 200
        assert (
            client.post(
                f"{base}/upload",
                files={"file": ("demo.pdf", b"%PDF", "application/pdf")},
                data={"customer_name": "中国电信"},
            ).status_code
            == 201
        )
        assert client.post(f"{base}/upload-tags", files={"file": ("tags.xlsx", b"PK\x03\x04")}).status_code == 200
        assert client.get(f"{base}/{fid}").status_code == 200
        assert client.get(f"{base}/{fid}/preview").status_code == 200
        assert client.get(f"{base}/{fid}/content").status_code == 200
        assert client.head(f"{base}/{fid}/content").status_code == 200
        assert client.get(f"{base}/{fid}/download").status_code == 200
        # 仅有 EXPORT 但无独立下载权，或仅有下载权但无子库查看权，均拒绝下载
        app.dependency_overrides[get_library_access] = lambda: LibraryAccess(level="EXPORT", allow_download=False)
        assert client.get(f"{base}/{fid}/download").status_code == 403
        app.dependency_overrides[get_library_access] = lambda: LibraryAccess(level="NONE", allow_download=True)
        assert client.get(f"{base}/{fid}/download").status_code == 403
        app.dependency_overrides[get_library_access] = lambda: FULL_LIB_ACCESS
        assert client.post(f"{base}/{fid}/favorite").json()["data"]["is_favorited"] is True
        assert client.delete(f"{base}/{fid}/favorite").status_code == 200
        assert client.get(f"{base}/{fid}/logs").status_code == 200
        assert client.patch(f"{base}/{fid}", json={"version": 1, "remark": "ok"}).status_code == 200
        assert client.patch(f"{base}/{fid}", json={"version": 1, "unknown_col": "x"}).status_code == 422
        assert client.delete(f"{base}/{fid}").json()["data"]["deleted"] is True

        monkeypatch.setattr(library_routes.read_service, "search_options", AsyncMock(side_effect=KeyError("bad")))
        assert client.get(f"{base}/options/search", params={"field": "bad"}).status_code == 422
    finally:
        app.dependency_overrides.clear()
