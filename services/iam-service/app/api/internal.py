from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from platform_common.internal_calls import verify_internal_caller
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AuthorizeRequest
from app.api.security import classified, principal_from_access_token
from app.application import outbox_delivery
from app.application.authorization import authorize_access_context
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.http_utils import success_json
from app.core.jwt_keys import build_jwks, ensure_jwt_keys
from app.domain.enums import SecurityClass

router = APIRouter(prefix="/internal/v1", tags=["internal"])


def require_internal_caller(request: Request, settings: Settings) -> str:
    return verify_internal_caller(request, settings.internal_caller_secrets)


@router.get("/jwks")
@classified(SecurityClass.INTERNAL)
async def jwks(settings: Settings = Depends(get_settings)) -> JSONResponse:
    meta = ensure_jwt_keys(settings.jwt_keys_path, allow_generate=settings.allow_generate_jwt_keys)
    return JSONResponse(build_jwks(settings.jwt_keys_path, meta))


@router.post("/authorize")
@classified(SecurityClass.INTERNAL)
async def authorize(
    body: AuthorizeRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    require_internal_caller(request, settings)
    principal = await principal_from_access_token(body.access_token, session, settings)
    data = await authorize_access_context(session, principal.user, body.resource, body.action)
    return success_json(data)


@router.get("/outbox/metrics")
@classified(SecurityClass.INTERNAL)
async def outbox_metrics(
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    require_internal_caller(request, settings)
    return success_json(await outbox_delivery.metrics(session))
