"""知识库全量历史数据与样本初始化（支持从压缩快照导入 1,448 条资料、7,648 条操作日志与收藏）。"""

from __future__ import annotations

import gzip
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.domain.models import KnowledgeFavorite, KnowledgeFile, KnowledgeOpLog

_NS = uuid.UUID("7f3b81d0-2c4e-49a1-9b0f-1a2b3c4d5e6f")
_SNAPSHOT_PATH = Path(__file__).resolve().parents[3] / "data" / "legacy_knowledge.json.gz"

# 当环境中不存在离线快照时的兜底最小样本（测试与空包保护）
_FALLBACK_RECORDS: tuple[dict[str, Any], ...] = (
    {
        "file_name": "场景化专线产品培训手册-政企双线专班-2026.6.pdf",
        "file_type": "产品",
        "operator_type": "电信",
        "depart_affiliation": "政企双线专班",
        "industry_type": "无",
        "app_scenario": "无",
        "market_category": "无",
        "product_type": "网",
        "product_sub_type": "智算专线|多云专线|量子保密专线",
        "prov_name": "集团",
        "data_time": "2026/6",
        "uploaded_at": "2026-10-21T05:39:47+00:00",
        "file_suffix": "PDF",
        "file_size_bytes": 4982681,
        "storage_path": "",
        "is_defined": True,
        "created_by_id": "seed",
        "created_by_name": "系统初始化",
    },
)


def _dt(text: str) -> datetime:
    if "T" in text:
        return datetime.fromisoformat(text).astimezone(UTC)
    return datetime.fromisoformat(text.replace(" ", "T") + "+08:00").astimezone(UTC)


def load_snapshot(snapshot_path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    target = snapshot_path or _SNAPSHOT_PATH
    if target.is_file():
        with gzip.open(target, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
        return {
            "files": list(data.get("files", [])),
            "logs": list(data.get("logs", [])),
            "favorites": list(data.get("favorites", [])),
        }
    return {
        "files": [
            {
                **item,
                "id": str(uuid.uuid5(_NS, f"fallback:{item['file_name']}")),
                "created_at": item["uploaded_at"],
                "updated_at": item["uploaded_at"],
                "updated_by_id": item["created_by_id"],
                "updated_by_name": item["created_by_name"],
            }
            for item in _FALLBACK_RECORDS
        ],
        "logs": [],
        "favorites": [],
    }


def _build_file_row(item: dict[str, Any]) -> KnowledgeFile:
    ts_created = _dt(str(item.get("created_at") or item["uploaded_at"]))
    ts_uploaded = _dt(str(item["uploaded_at"]))
    ts_updated = _dt(str(item.get("updated_at") or item["uploaded_at"]))
    file_type = str(item.get("file_type") or "")
    name = str(item["file_name"])
    return KnowledgeFile(
        id=uuid.UUID(str(item["id"])),
        file_name=name,
        file_type=file_type,
        operator_type=str(item.get("operator_type") or ""),
        depart_affiliation=str(item.get("depart_affiliation") or ""),
        industry_type=str(item.get("industry_type") or ""),
        app_scenario=str(item.get("app_scenario") or ""),
        market_category=str(item.get("market_category") or ""),
        product_type=str(item.get("product_type") or ""),
        product_sub_type=str(item.get("product_sub_type") or ""),
        prov_name=str(item.get("prov_name") or ""),
        data_time=str(item.get("data_time") or ""),
        uploaded_at=ts_uploaded,
        file_suffix=str(item.get("file_suffix") or ""),
        file_size_bytes=int(item.get("file_size_bytes") or 0),
        storage_path=str(item.get("storage_path") or ""),
        content_text="",
        remark=str(item.get("remark") or ""),
        is_defined=bool(item.get("is_defined", bool(file_type))),
        version=1,
        created_at=ts_created,
        created_by_id=str(item.get("created_by_id") or "legacy")[:64],
        created_by_name=str(item.get("created_by_name") or "历史用户")[:128],
        updated_at=ts_updated,
        updated_by_id=str(item.get("updated_by_id") or "legacy")[:64],
        updated_by_name=str(item.get("updated_by_name") or "历史用户")[:128],
    )


async def _existing_uuid_set(session: AsyncSession, column: Any) -> set[uuid.UUID]:
    rows = (await session.execute(select(column))).scalars()
    return set(rows)


async def ensure_seed_data(
    session: AsyncSession,
    *,
    force: bool = False,
    snapshot_path: Path | None = None,
    user_map: dict[str, str] | None = None,
) -> dict[str, int]:
    """幂等导入知识库资料、历史操作日志与历史收藏。库内已有数据时默认跳过，传 force=True 按主键补齐。"""

    existing_count = int(await session.scalar(select(func.count()).select_from(KnowledgeFile)) or 0)
    if existing_count > 0 and not force:
        return {"files": 0, "logs": 0, "favorites": 0}

    data = load_snapshot(snapshot_path)
    existing_files = await _existing_uuid_set(session, KnowledgeFile.id) if existing_count else set()
    new_files = [_build_file_row(item) for item in data["files"] if uuid.UUID(str(item["id"])) not in existing_files]
    if new_files:
        session.add_all(new_files)
        await session.flush()

    known_files = existing_files | {row.id for row in new_files}
    existing_logs = await _existing_uuid_set(session, KnowledgeOpLog.id) if existing_count else set()
    new_logs = [
        KnowledgeOpLog(
            id=uuid.UUID(str(log["id"])),
            file_id=uuid.UUID(str(log["file_id"])),
            actor_id=str(log.get("actor_id") or "legacy")[:64],
            actor_name=str(log.get("actor_name") or "历史用户")[:128],
            op_type=str(log.get("op_type") or "操作")[:32],
            detail=str(log.get("detail") or "")[:500],
            created_at=_dt(str(log["created_at"])),
        )
        for log in data["logs"]
        if uuid.UUID(str(log["id"])) not in existing_logs and uuid.UUID(str(log["file_id"])) in known_files
    ]
    if new_logs:
        session.add_all(new_logs)

    resolved_map = user_map or {}
    existing_favs = (
        {(r[0], r[1]) for r in (await session.execute(select(KnowledgeFavorite.user_id, KnowledgeFavorite.file_id)))}
        if existing_count
        else set()
    )
    new_favs: list[KnowledgeFavorite] = []
    seen_fav_keys = set(existing_favs)
    for fav in data["favorites"]:
        fid = uuid.UUID(str(fav["file_id"]))
        if fid not in known_files:
            continue
        account = str(fav.get("account") or fav.get("legacy_user_id") or "legacy")
        target_uid = (resolved_map.get(account) or f"legacy:{account}")[:64]
        key = (target_uid, fid)
        if key in seen_fav_keys:
            continue
        seen_fav_keys.add(key)
        new_favs.append(KnowledgeFavorite(user_id=target_uid, file_id=fid, created_at=_dt(str(fav["created_at"]))))
    if new_favs:
        session.add_all(new_favs)

    await session.flush()
    return {"files": len(new_files), "logs": len(new_logs), "favorites": len(new_favs)}
