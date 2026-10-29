"""任务调度页的接口。路由由公共调度引擎生成，资源 system.scheduler。"""

from platform_common.scheduler import build_scheduler_router

from app.common.security import check_permission, require_policy_permission
from app.core.database import get_db_session
from app.scheduler.application.jobs import scheduler

router = build_scheduler_router(
    scheduler,
    prefix="/api/v1/policy/scheduled-jobs",
    require_permission=require_policy_permission,
    get_db_session=get_db_session,
    check_permission=check_permission,
)
