"""任务调度页上 IAM 的任务。路由由公共调度引擎生成，资源 system.scheduler 由本服务直接判权。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends
from platform_common.actors import Actor
from platform_common.route_audit import mark_permission_dependency
from platform_common.scheduler import build_scheduler_router

from app.api.security import CurrentPrincipal, require_permission
from app.application.scheduled_jobs import scheduler
from app.core.database import get_db_session


def require_actor(resource: str, action: str) -> Callable[..., Any]:
    """公共路由要的是 Actor：判权照旧走本服务的 require_permission，再换成显示名。"""

    async def dependency(principal: CurrentPrincipal = Depends(require_permission(resource, action))) -> Actor:
        return Actor(id=str(principal.user.id), name=principal.user.display_name)

    return mark_permission_dependency(dependency, resource=resource, action=action)


router = build_scheduler_router(
    scheduler, prefix="/api/v1/system/scheduled-jobs", require_permission=require_actor, get_db_session=get_db_session
)
