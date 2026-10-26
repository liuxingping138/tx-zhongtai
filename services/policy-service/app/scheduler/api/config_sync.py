"""爬虫配置统计页上的「立即同步」：往调度队列里放一次爬虫配置同步，页面轮询状态。

授权用统计页的资源（policy.crawler_config 完整档），看统计的人不需要任务调度页的权限；
执行仍走调度队列和 policy-worker，HTTP 进程不连爬虫库。
"""

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.security import classified, require_policy_permission
from app.core.database import get_db_session
from app.scheduler.application.jobs import scheduler
from app.scheduler.domain.scheduling import CRAWLER_CONFIG

router = APIRouter(prefix="/api/v1/policy/crawler-config/sync", tags=["policy-crawler-config"])
RESOURCE = "policy.crawler_config"


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def sync_status(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(jsonable_encoder(await scheduler.run_status(session, CRAWLER_CONFIG)))


@router.post("", status_code=202)
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def trigger_sync(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "sync")),
) -> JSONResponse:
    return success_json(jsonable_encoder(await scheduler.trigger_job(session, CRAWLER_CONFIG, actor)), status_code=202)
