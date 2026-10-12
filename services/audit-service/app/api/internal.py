from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import classified, require_internal_caller
from app.application.ingest import ingest_event
from app.application.schemas import IngestRequest
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.http_utils import success_json
from app.domain.enums import SecurityClass

router = APIRouter(prefix="/internal/v1", tags=["internal"])


@router.post("/audit/events")
@classified(SecurityClass.INTERNAL)
async def ingest_audit_event(
    body: IngestRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    source_service = require_internal_caller(request, settings)
    result = await ingest_event(
        session,
        source_service=source_service,
        body=body,
        max_bytes=settings.max_event_bytes,
    )
    return success_json({"event_id": str(result.event_id), "duplicate": result.duplicate})
