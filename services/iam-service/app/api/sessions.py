"""在线用户：全部有效登录（没撤销、没过期的会话），标出 30 分钟内有操作的为在线；按设备下线。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import CurrentPrincipal, classified, require_permission
from app.application import session_admin
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.http_utils import success_json
from app.domain.enums import SecurityClass

router = APIRouter()


@router.get("/sessions")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_sessions(
    principal: CurrentPrincipal = Depends(require_permission("system.users", "list")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    return success_json(
        await session_admin.list_online(
            session,
            principal.user,
            current_session_id=principal.session.id,
            online_window_seconds=settings.online_window_seconds,
        )
    )


@router.delete("/sessions/{session_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def revoke_session(
    session_id: uuid.UUID,
    principal: CurrentPrincipal = Depends(require_permission("system.users", "revoke_sessions")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    await session_admin.revoke_one(session, principal.user, session_id, current_session_id=principal.session.id)
    return success_json({"revoked": True})
