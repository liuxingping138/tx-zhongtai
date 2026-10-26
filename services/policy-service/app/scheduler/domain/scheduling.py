"""本服务调度的常量。时间、重试规则在 platform_common.scheduler。"""

from app.crawlconfig.domain.models import JOB_CODE

CRAWLER = "crawler"
CRAWLER_CONFIG = JOB_CODE
LEADER_LOCK = 72120260929
