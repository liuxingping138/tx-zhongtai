"""访问白名单（系统管理，资源 system.ip_whitelist）：限定公司网络的模块，别处要给这个人按 IP 开有时效的白名单。

这组接口在 IAM 里，本身不受网络限制：管理员人在外面、或公司出口 IP 变了时，还能登录进来处理。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from platform_common.http_utils import client_ip
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import StrictModel
from app.api.security import CurrentPrincipal, classified, require_permission
from app.application import ip_whitelist as service
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.http_utils import success_json
from app.domain.enums import SecurityClass

router = APIRouter()
RESOURCE = "system.ip_whitelist"


class WhitelistBody(StrictModel):
    user_id: uuid.UUID = Field(description="给谁开通")
    ip_range: str = Field(min_length=1, max_length=64, description="单个 IP，或不宽于 /24 的网段")
    reason: str = Field(default="", max_length=500, description="开通原因")
    expires_at: datetime = Field(description="到期时间；不带时区按北京时间")

    def to_input(self) -> service.WhitelistInput:
        return service.WhitelistInput(
            user_id=self.user_id, ip_range=self.ip_range, reason=self.reason, expires_at=self.expires_at
        )


@router.get("/ip-whitelist")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_whitelist(
    request: Request,
    principal: CurrentPrincipal = Depends(require_permission(RESOURCE, "list")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    return success_json(await service.overview(session, settings, actor=principal.user, ip=client_ip(request)))


@router.get("/ip-whitelist/user-options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def whitelist_user_options(
    keyword: str = Query(default="", max_length=64),
    _: CurrentPrincipal = Depends(require_permission(RESOURCE, "list")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    return success_json({"items": await service.user_options(session, keyword)})


@router.post("/ip-whitelist")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_whitelist(
    body: WhitelistBody,
    principal: CurrentPrincipal = Depends(require_permission(RESOURCE, "create")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    return success_json(await service.create_entry(session, settings, actor=principal.user, data=body.to_input()))


@router.put("/ip-whitelist/{entry_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_whitelist(
    entry_id: uuid.UUID,
    body: WhitelistBody,
    principal: CurrentPrincipal = Depends(require_permission(RESOURCE, "update")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    return success_json(
        await service.update_entry(session, settings, actor=principal.user, entry_id=entry_id, data=body.to_input())
    )


@router.delete("/ip-whitelist/{entry_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def delete_whitelist(
    entry_id: uuid.UUID,
    principal: CurrentPrincipal = Depends(require_permission(RESOURCE, "delete")),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    await service.delete_entry(session, actor=principal.user, entry_id=entry_id)
    return success_json({"id": str(entry_id)})
