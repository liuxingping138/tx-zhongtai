"""智库专属 6 张码表：规格、迁移种子、CRUD、乐观锁、去重、导入导出、筛选项、内部接口与审计。"""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from platform_common.actors import Actor
from platform_common.errors import ApiError, NotFoundError, VersionConflictError
from platform_common.internal_calls import internal_headers
from platform_common.route_audit import iter_api_routes, permission_map
from sqlalchemy.dialects import postgresql

from app.api import internal as internal_api
from app.api import thinktank_dicts as dicts_api
from app.application import audit_emit, code_tables
from app.application import thinktank_dicts as service
from app.core.config import get_settings
from app.core.database import get_db_session
from app.domain.models import ThinktankDict
from app.domain.thinktank_dicts import THINKTANK_DICT_BY_TYPE, THINKTANK_DICT_SPECS
from app.main import app
from app.repositories import options as options_repo
from app.repositories import thinktank_dicts as repo

ACTOR = Actor(id="u-1", name="测试员")
NOW = datetime(2026, 11, 27, tzinfo=UTC)


class _Session:
    def __init__(
        self, *, scalar_val: Any = 0, scalars_val: list[Any] | None = None, rows_val: list[Any] | None = None
    ) -> None:
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.executed: list[Any] = []
        self.flush = AsyncMock()
        self._scalar_val = scalar_val
        self._scalars_val = list(scalars_val or [])
        self._rows_val = list(rows_val or [])

    def add(self, row: Any) -> None:
        row.id = row.id or uuid.uuid4()
        self.added.append(row)

    async def delete(self, row: Any) -> None:
        self.deleted.append(row)

    async def scalar(self, stmt: Any) -> Any:
        self.executed.append(stmt)
        return self._scalar_val

    async def execute(self, stmt: Any) -> Any:
        self.executed.append(stmt)
        scalars_val = self._scalars_val
        rows_val = self._rows_val

        class _Res:
            rowcount = len(rows_val) or 83

            def scalar_one_or_none(self) -> Any:
                return scalars_val[0] if scalars_val else None

            def scalars(self) -> list[Any]:
                return list(scalars_val)

            def all(self) -> list[Any]:
                return list(rows_val)

        return _Res()


def _row(dict_type: str = "file_types", name: str = "经分", sort_order: int = 1, version: int = 1) -> ThinktankDict:
    return ThinktankDict(
        id=uuid.uuid4(),
        dict_type=dict_type,
        name=name,
        sort_order=sort_order,
        version=version,
        created_at=NOW,
        created_by_id="u-1",
        created_by_name="测试员",
        updated_at=NOW,
        updated_by_id="u-1",
        updated_by_name="测试员",
    )


def _xlsx(header: list[str], rows: list[list[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(header)
    for line in rows:
        sheet.append(line)
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()


def _events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    async def fake_enqueue(_session: Any, **kwargs: Any) -> None:
        captured.append(kwargs)

    monkeypatch.setattr(service, "enqueue_event", fake_enqueue)
    return captured


def test_specs_seed_counts_audit_meta_and_migration_alignment() -> None:
    expected_counts = {
        "file_types": 14,
        "departments": 9,
        "industries": 12,
        "product_types": 12,
        "provinces": 32,
        "market_categories": 4,
    }
    assert {spec.dict_type: len(spec.seed_values) for spec in THINKTANK_DICT_SPECS} == expected_counts
    for spec in THINKTANK_DICT_SPECS:
        assert len(set(spec.seed_values)) == len(spec.seed_values)
        for suffix, action in (
            ("created", "create"),
            ("updated", "update"),
            ("deleted", "delete"),
            ("imported", "import"),
            ("exported", "export"),
        ):
            meta = audit_emit._EVENT_META[f"codebook.thinktank.{spec.dict_type}.{suffix}"]
            assert meta[0] == spec.resource
            assert meta[1] == action

    # 校验迁移文件与域定义种子完全一致且挂在 c9d8e9f0a107 之后。
    mig_path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "d0e9f0a1b208_thinktank_dicts.py"
    spec_obj = importlib.util.spec_from_file_location("d0e9f0a1b208_thinktank_dicts", mig_path)
    assert spec_obj and spec_obj.loader
    mod = importlib.util.module_from_spec(spec_obj)
    spec_obj.loader.exec_module(mod)
    assert mod.down_revision == "c9d8e9f0a107"
    assert dict(mod._INITIAL_SEEDS) == {s.dict_type: s.seed_values for s in THINKTANK_DICT_SPECS}
    # AI 模板码表清单保持原样，不混入智库码表。
    assert set(code_tables.CODE_TABLES) == {"policy_types", "scenarios", "scenario_l1"}


class TestThinktankDictService:
    @pytest.fixture
    def env(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        state = SimpleNamespace(row=None, by_name=None, events=_events(monkeypatch))
        monkeypatch.setattr(service.repo, "get_by_name", AsyncMock(side_effect=lambda *_, **__: state.by_name))
        monkeypatch.setattr(service.repo, "get_for_update", AsyncMock(side_effect=lambda *_: state.row))
        return state

    async def test_create_validation_duplicate_and_audit(self, env: SimpleNamespace) -> None:
        session = _Session()
        out = await service.create_dict(session, ACTOR, "file_types", {"name": " 专项报告 ", "sort_order": 5})  # type: ignore[arg-type]
        assert (out["dict_type"], out["name"], out["sort_order"], out["version"]) == ("file_types", "专项报告", 5, 1)
        assert env.events[-1]["event_type"] == "codebook.thinktank.file_types.created"

        with pytest.raises(ApiError, match="文件类别不能为空") as err:
            await service.create_dict(session, ACTOR, "file_types", {"name": "  "})  # type: ignore[arg-type]
        assert err.value.http_status == 422

        with pytest.raises(ApiError, match="超过 128 字") as err:
            await service.create_dict(session, ACTOR, "file_types", {"name": "长" * 129})  # type: ignore[arg-type]
        assert err.value.http_status == 422

        env.by_name = object()
        with pytest.raises(ApiError, match="文件类别已存在") as err:
            await service.create_dict(session, ACTOR, "file_types", {"name": "经分"})  # type: ignore[arg-type]
        assert err.value.http_status == 409 and err.value.code == "DUPLICATE"

        with pytest.raises(NotFoundError):
            await service.create_dict(session, ACTOR, "unknown_type", {"name": "x"})  # type: ignore[arg-type]

    async def test_update_optimistic_lock_duplicate_and_noop(self, env: SimpleNamespace) -> None:
        session = _Session()
        with pytest.raises(NotFoundError):
            await service.update_dict(session, ACTOR, "provinces", uuid.uuid4(), {"version": 1, "name": "新省"})  # type: ignore[arg-type]

        env.row = _row("provinces", "北京市", sort_order=2, version=1)
        with pytest.raises(VersionConflictError):
            await service.update_dict(session, ACTOR, "provinces", env.row.id, {"version": 9, "name": "北京"})  # type: ignore[arg-type]

        with pytest.raises(ApiError, match="省份名称不能为空"):
            await service.update_dict(session, ACTOR, "provinces", env.row.id, {"version": 1, "name": " "})  # type: ignore[arg-type]

        env.by_name = SimpleNamespace(id=uuid.uuid4())
        with pytest.raises(ApiError, match="省份名称已存在") as dup:
            await service.update_dict(session, ACTOR, "provinces", env.row.id, {"version": 1, "name": "上海市"})  # type: ignore[arg-type]
        assert dup.value.http_status == 409 and dup.value.code == "DUPLICATE"

        env.by_name = None
        same = await service.update_dict(session, ACTOR, "provinces", env.row.id, {"version": 1, "name": "北京市"})  # type: ignore[arg-type]
        assert same["version"] == 1 and env.events == []

        updated = await service.update_dict(
            session, ACTOR, "provinces", env.row.id, {"version": 1, "name": "北京市(新)", "sort_order": 3}
        )  # type: ignore[arg-type]
        assert (updated["name"], updated["sort_order"], updated["version"]) == ("北京市(新)", 3, 2)
        assert env.events[-1]["event_type"] == "codebook.thinktank.provinces.updated"

    async def test_delete_missing_and_success(self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
        session = _Session()
        with pytest.raises(NotFoundError):
            await service.delete_dict(session, ACTOR, "departments", uuid.uuid4())  # type: ignore[arg-type]

        env.row = _row("departments", "政企部")
        deleted_rows: list[Any] = []
        monkeypatch.setattr(service.repo, "delete_item", AsyncMock(side_effect=lambda _s, r: deleted_rows.append(r)))
        out = await service.delete_dict(session, ACTOR, "departments", env.row.id)  # type: ignore[arg-type]
        assert out == {"deleted": True}
        assert deleted_rows == [env.row]
        assert env.events[-1]["event_type"] == "codebook.thinktank.departments.deleted"

    async def test_export_builds_single_business_column_and_enforces_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events = _events(monkeypatch)
        monkeypatch.setattr(service.repo, "count_filtered", AsyncMock(return_value=10**7))
        with pytest.raises(ApiError, match="超过单次导出上限") as err:
            await service.export_dicts(_Session(), ACTOR, "industries", {"keyword": ["金融"]})  # type: ignore[arg-type]
        assert err.value.http_status == 422 and "筛选结果" in err.value.message

        monkeypatch.setattr(service.repo, "count_filtered", AsyncMock(return_value=1))
        monkeypatch.setattr(service.repo, "list_filtered", AsyncMock(return_value=[_row("industries", "金融")]))
        payload = await service.export_dicts(_Session(), ACTOR, "industries", {})  # type: ignore[arg-type]
        sheet = load_workbook(BytesIO(payload)).active
        assert sheet is not None
        rows = [[cell.value for cell in line] for line in sheet.iter_rows()]
        assert rows[0] == ["行业类别", "入库时间", "入库人", "更新时间", "操作人"]
        assert rows[1][0] == "金融"
        assert events[-1]["event_type"] == "codebook.thinktank.industries.exported"

    async def test_import_accepts_label_or_generic_name_and_skips_invalid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events = _events(monkeypatch)
        monkeypatch.setattr(service.repo, "existing_names", AsyncMock(return_value={"云"}))
        # 表头用专属中文名「产品类别」
        content = _xlsx(
            ["产品类别", "备注"],
            [
                ["云", "已存在"],
                ["边缘计算", "新增"],
                ["边缘计算", "文件内重复"],
                [" ", "空白"],
                ["超" * 129, "超长"],
            ],
        )
        session = _Session()
        result = await service.import_dicts(session, ACTOR, "product_types", content)  # type: ignore[arg-type]
        assert (result["inserted"], result["updated"], result["skipped"], result["total"]) == (1, 0, 4, 5)
        assert [row.name for row in session.added] == ["边缘计算"]
        assert result["skipped_file"] is not None
        assert events[-1]["event_type"] == "codebook.thinktank.product_types.imported"

        # 表头用通用「名称」也能正常识别，且全部通过时 skipped_file 为 None
        monkeypatch.setattr(service.repo, "existing_names", AsyncMock(return_value=set()))
        clean_xlsx = _xlsx(["名称"], [["政企专项"]])
        clean = await service.import_dicts(_Session(), ACTOR, "market_categories", clean_xlsx)  # type: ignore[arg-type]
        assert (clean["inserted"], clean["skipped"], clean["skipped_file"]) == (1, 0, None)

    async def test_seed_thinktank_dicts_passes_all_83_rows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[dict[str, Any]] = []

        async def fake_insert(_session: Any, rows: list[dict[str, Any]]) -> int:
            captured.extend(rows)
            return len(rows)

        monkeypatch.setattr(service.repo, "insert_seed_rows", fake_insert)
        inserted = await service.seed_thinktank_dicts(_Session())  # type: ignore[arg-type]
        assert inserted == 83
        assert len(captured) == 83
        by_type = {
            spec.dict_type: [r for r in captured if r["dict_type"] == spec.dict_type] for spec in THINKTANK_DICT_SPECS
        }
        assert [r["sort_order"] for r in by_type["market_categories"]] == [1, 2, 3, 4]
        assert [r["name"] for r in by_type["market_categories"]] == ["行客", "商客", "综合", "无"]


async def test_repository_queries_and_options() -> None:
    with pytest.raises(KeyError):
        repo._conditions("provinces", {"bad_field": "x"})
    conds = repo._conditions("provinces", {"keyword": ["北京", "上海"]})
    assert len(conds) == 2
    sql = str(conds[1].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "北京" in sql and "上海" in sql

    row = _row("provinces", "北京市")
    session = _Session(scalar_val=1, scalars_val=[row], rows_val=[("provinces", "北京市"), ("file_types", "经分")])
    items, total = await repo.list_items(session, "provinces", filters={"keyword": None}, page=1, page_size=20)  # type: ignore[arg-type]
    assert total == 1 and items == [row]
    assert await repo.count_filtered(session, "provinces", {}) == 1  # type: ignore[arg-type]
    assert await repo.list_filtered(session, "provinces", {}) == [row]  # type: ignore[arg-type]
    assert await repo.get_for_update(session, "provinces", row.id) == row  # type: ignore[arg-type]
    assert await repo.get_by_name(session, "provinces", "北京市", lock=True) == row  # type: ignore[arg-type]
    assert await repo.existing_names(session, "provinces", []) == set()  # type: ignore[arg-type]
    assert await repo.existing_names(session, "provinces", ["北京市"]) == {row}  # type: ignore[arg-type]
    grouped = await repo.list_all_grouped(session)  # type: ignore[arg-type]
    assert grouped["provinces"] == ["北京市"] and grouped["file_types"] == ["经分"] and grouped["industries"] == []
    await repo.delete_item(session, row)  # type: ignore[arg-type]
    assert session.deleted == [row]
    assert await repo.insert_seed_rows(session, []) == 0  # type: ignore[arg-type]
    assert await repo.insert_seed_rows(session, [{"dict_type": "provinces", "name": "集团"}]) == 2  # type: ignore[arg-type]

    opt_session = _Session(scalars_val=["集团", "北京市"])
    opts = await options_repo.thinktank_dict_options(opt_session, "provinces")  # type: ignore[arg-type]
    assert opts == {"options": {"name": {"items": ["集团", "北京市"], "truncated": False}}}
    found = await options_repo.search_thinktank_dict_options(opt_session, "provinces", field="name", keyword="北")  # type: ignore[arg-type]
    assert found == ["集团", "北京市"]


def _override_all_routes_for_test() -> None:
    async def _db() -> AsyncIterator[object]:
        yield object()

    app.dependency_overrides[get_db_session] = _db
    for route in iter_api_routes(app):
        if route.path.startswith("/api/v1/codebook/thinktank/"):
            for dep in route.dependant.dependencies:
                if dep.call is not get_db_session and dep.call is not get_settings:
                    app.dependency_overrides[dep.call] = lambda: ACTOR


def test_http_routes_permission_matrix() -> None:
    mapping = permission_map(app)
    for spec in THINKTANK_DICT_SPECS:
        base = f"/api/v1/codebook/thinktank/{spec.slug}"
        assert mapping[f"GET {base}"] == (spec.resource, "list")
        assert mapping[f"GET {base}/options"] == (spec.resource, "list")
        assert mapping[f"GET {base}/options/search"] == (spec.resource, "list")
        assert mapping[f"GET {base}/export"] == (spec.resource, "export")
        assert mapping[f"POST {base}/import"] == (spec.resource, "import")
        assert mapping[f"POST {base}"] == (spec.resource, "create")
        assert mapping[f"PATCH {base}/{{item_id}}"] == (spec.resource, "update")
        assert mapping[f"DELETE {base}/{{item_id}}"] == (spec.resource, "delete")


def test_http_routes_end_to_end_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    _override_all_routes_for_test()
    try:
        item_id = uuid.uuid4()
        sample = {"id": str(item_id), "dict_type": "provinces", "name": "北京市", "sort_order": 2, "version": 1}
        monkeypatch.setattr(
            dicts_api.service,
            "list_dicts",
            AsyncMock(return_value={"items": [sample], "total": 1, "page": 1, "page_size": 20}),
        )
        monkeypatch.setattr(
            dicts_api.service,
            "list_dict_options",
            AsyncMock(return_value={"options": {"name": {"items": ["北京市"], "truncated": False}}}),
        )

        async def fake_search(_s: Any, _dt: str, *, field: str, keyword: str | None) -> list[str]:
            if field != "name":
                raise KeyError(field)
            return ["北京市"]

        monkeypatch.setattr(dicts_api.service, "search_dict_options", fake_search)
        monkeypatch.setattr(dicts_api.service, "export_dicts", AsyncMock(return_value=b"xlsx-bytes"))
        monkeypatch.setattr(
            dicts_api.service,
            "import_dicts",
            AsyncMock(return_value={"inserted": 2, "updated": 0, "skipped": 0, "total": 2, "skipped_file": None}),
        )
        monkeypatch.setattr(dicts_api.service, "create_dict", AsyncMock(return_value=sample))
        captured_patch: dict[str, Any] = {}

        async def fake_update(_s: Any, _a: Any, dt: str, iid: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
            captured_patch["dict_type"] = dt
            captured_patch["data"] = data
            return {**sample, "version": 2}

        monkeypatch.setattr(dicts_api.service, "update_dict", fake_update)
        monkeypatch.setattr(dicts_api.service, "delete_dict", AsyncMock(return_value={"deleted": True}))

        client = TestClient(app)
        base = "/api/v1/codebook/thinktank/provinces"
        assert client.get(base).json()["data"]["total"] == 1
        assert client.get(f"{base}/options").json()["data"]["options"]["name"]["items"] == ["北京市"]
        assert client.get(f"{base}/options/search", params={"field": "name", "q": "北"}).json()["data"]["items"] == [
            "北京市"
        ]
        assert client.get(f"{base}/options/search", params={"field": "bad"}).status_code == 422

        exp = client.get(f"{base}/export")
        assert exp.status_code == 200 and exp.content == b"xlsx-bytes"
        assert 'filename="thinktank-provinces.xlsx"' in exp.headers["content-disposition"]
        assert "filename*=UTF-8''" in exp.headers["content-disposition"]

        unauth_imp = client.post(
            f"{base}/import",
            files={
                "file": ("provinces.xlsx", b"fake", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            },
        )
        assert unauth_imp.status_code == 401
        imp = client.post(
            f"{base}/import",
            headers={"Authorization": "Bearer test-token"},
            files={
                "file": ("provinces.xlsx", b"fake", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            },
        )
        assert imp.status_code == 200 and imp.json()["data"]["inserted"] == 2

        created = client.post(base, json={"name": "北京市", "sort_order": 2})
        assert created.status_code == 201 and created.json()["data"]["name"] == "北京市"

        patched = client.patch(f"{base}/{item_id}", json={"version": 1, "sort_order": 9})
        assert patched.status_code == 200 and captured_patch == {
            "dict_type": "provinces",
            "data": {"version": 1, "sort_order": 9},
        }

        deleted = client.delete(f"{base}/{item_id}")
        assert deleted.status_code == 200 and deleted.json()["data"] == {"deleted": True}
    finally:
        app.dependency_overrides.clear()


def test_internal_thinktank_dicts_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _db() -> AsyncIterator[object]:
        yield object()

    expected = {spec.dict_type: list(spec.seed_values[:2]) for spec in THINKTANK_DICT_SPECS}
    monkeypatch.setattr(internal_api.thinktank_dicts, "get_all_thinktank_dicts", AsyncMock(return_value=expected))
    settings = get_settings().model_copy(update={"internal_caller_secrets": {"thinktank-service": "tt-secret"}})
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        client = TestClient(app)
        assert client.get("/internal/v1/thinktank-dicts").status_code == 401
        assert (
            client.get(
                "/internal/v1/thinktank-dicts", headers=internal_headers("thinktank-service", "wrong")
            ).status_code
            == 401
        )
        ok = client.get("/internal/v1/thinktank-dicts", headers=internal_headers("thinktank-service", "tt-secret"))
        assert ok.status_code == 200
        assert ok.json()["data"] == expected
        assert set(ok.json()["data"]) == set(THINKTANK_DICT_BY_TYPE)
    finally:
        app.dependency_overrides.clear()
