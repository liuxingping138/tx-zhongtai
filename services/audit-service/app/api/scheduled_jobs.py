"""任务调度页上审计服务的任务。路由由公共调度引擎生成，资源 system.scheduler 经 IAM 判权。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from platform_common.scheduler import build_scheduler_router
from platform_common.service_authz import build_permission_dependency

from app.api.security import get_authz_client
from app.application.scheduled_jobs import scheduler
from app.core.database import get_db_session

require_permission: Callable[[str, str], Callable[..., Any]] = build_permission_dependency(get_authz_client)

router = build_scheduler_router(
    scheduler,
    prefix="/api/v1/audit/scheduled-jobs",
    require_permission=require_permission,
    get_db_session=get_db_session,
)
