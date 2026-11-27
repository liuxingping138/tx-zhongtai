"""访问白名单维护接口（资源 thinktank.ip_whitelist）。

这组接口不挂网络准入：公司出口 IP 变了、或管理员人在外面时，还能登录后把自己或同事加进来；
能进来的前提仍然是有这个资源的权限，一般只授给管理员。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.http_utils import client_ip, success_json
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.application import whitelist as service
from app.common.security import classified, require_thinktank_permission
from app.core.config import Settings, get_settings
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/thinktank/ip-whitelist", tags=["thinktank-ip-whitelist"])
RESOURCE = "thinktank.ip_whitelist"


class WhitelistBody(BaseModel):
    ip_range: str = Field(min_length=1, max_length=64, description="单个 IP，或不宽于 /24 的网段")
    holder: str = Field(min_length=1, max_length=64, description="使用人")
    reason: str = Field(default="", max_length=500, description="开通原因")
    expires_at: datetime = Field(description="到期时间；不带时区按北京时间")

    def to_input(self) -> service.WhitelistInput:
        return service.WhitelistInput(
            ip_range=self.ip_range, holder=self.holder, reason=self.reason, expires_at=self.expires_at
        )


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_whitelist(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_thinktank_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.overview(session, settings, ip=client_ip(request)))


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_whitelist(
    body: WhitelistBody,
    settings: Annotated[Settings, Depends(get_settings)],
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "create")),
) -> JSONResponse:
    return success_json(await service.create_entry(session, settings, actor=actor, data=body.to_input()))


@router.put("/{entry_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_whitelist(
    entry_id: uuid.UUID,
    body: WhitelistBody,
    settings: Annotated[Settings, Depends(get_settings)],
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(
        await service.update_entry(session, settings, actor=actor, entry_id=entry_id, data=body.to_input())
    )


@router.delete("/{entry_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def delete_whitelist(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "delete")),
) -> JSONResponse:
    await service.delete_entry(session, actor=actor, entry_id=entry_id)
    return success_json({"id": str(entry_id)})
