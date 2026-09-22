"""policy-service 配置。环境变量前缀 `POLICY_`。"""

from __future__ import annotations

from functools import lru_cache

from platform_common.config import BaseServiceSettings, Environment
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(env_prefix="POLICY_", env_file=".env", extra="ignore")

    service_name: str = "policy-service"
    http_port: int = 8004
    database_url: str
    cors_allow_origins: list[str] = []

    iam_base_url: str = "http://iam-service:8001"
    iam_service_secret: str = ""
    iam_authorize_timeout_seconds: float = 2.0

    audit_ingest_url: str = "http://audit-service:8002"
    audit_ingest_secret: str = ""
    worker_poll_interval_seconds: float = 2.0
    worker_max_attempts: int = 8
    import_max_bytes: int = 20 * 1024 * 1024
    # 导出会把整表读进内存再生成 Excel，必须有上限，否则大表导出能把服务撑爆。
    export_max_rows: int = 100_000

    # 爬虫监测：只读连爬虫库做按天聚合，结果落本服务库。服务进程不连它，只有同步 CLI 用。
    crawler_mysql_host: str = ""
    crawler_mysql_port: int = 3306
    crawler_mysql_user: str = ""
    crawler_mysql_password: str = ""
    crawler_mysql_db: str = "crawler2021"
    crawler_data_table: str = "csys_policy_info_source_all"
    crawler_rules_table: str = "policy_rules_alls_spider"
    # 日常同步回算最近几天。爬虫是「采集后入库」，实测入库普遍比 collect_date 晚 1 天，
    # 近 60 天里最大滞后 4 天。窗口必须大于最大滞后，否则迟到的行进库时窗口已经滑过它的
    # collect_date，那天的统计会永久少算。7 天是在实测滞后上留了余量。
    crawler_sync_days: int = 7
    # 首次回填窗口。窗口外没出过数的任务一律按「长期断爬」处理，不再回查大表。
    crawler_backfill_days: int = 365
    # 健康分档阈值（停更天数）：<=normal 正常，<=watch 观察，其余断爬。
    crawler_health_normal_days: int = 7
    crawler_health_watch_days: int = 30

    @model_validator(mode="after")
    def _reject_demo_secrets_in_production(self) -> Settings:
        if self.environment == Environment.PRODUCTION:
            markers = ("dev-", "example", "changeme", "test-secret", "p6-only")
            for token in (self.iam_service_secret, self.audit_ingest_secret):
                if token and any(marker in token.lower() for marker in markers):
                    raise ValueError("生产环境内部调用密钥看起来是示例值，拒绝启动")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
