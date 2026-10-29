"""policy-service 配置。环境变量前缀 `POLICY_`。"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache

from platform_common.config import BaseServiceSettings, Environment
from pydantic import field_validator, model_validator
from pydantic_settings import SettingsConfigDict

# 爬虫库表名会拼进 SQL（表名不能参数绑定），只允许「库名.表名」形式的标识符。
_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


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
    # 配合最长 15 分钟的退避，审计服务连不上能容忍约一天才置 dead（原来 8 次、三四分钟就放弃）。
    worker_max_attempts: int = 100
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
    # 爬虫配置统计：爬虫同事维护的规则表，一行一个栏目，site_code 对应信源的网站编码。
    crawler_rules_table: str = "policy_rules_alls"
    # 2026-10-22 上线时统一给历史已爬网站补填的上线时间，不是真实配置日：这天上线的算期初存量，不计入任何一周。
    # 规则表里能关联上的网站，同步会把上线时间改成规则创建日期，剩下的才停在这天。
    crawler_config_backfill_date: date = date(2026, 10, 22)

    @field_validator("crawler_data_table", "crawler_rules_table")
    @classmethod
    def _table_name_is_identifier(cls, value: str) -> str:
        if not _TABLE_NAME.fullmatch(value):
            raise ValueError(f"爬虫库表名只能包含字母、数字、下划线：{value!r}")
        return value

    # 状态分档阈值（停更天数）：<=normal 正常，<=watch 关注，其余停更。
    crawler_health_normal_days: int = 7
    crawler_health_watch_days: int = 30

    # 政策 AI 打标：源数据在同一 MySQL 实例的 bid_analyse 库（政策表 + 正文表），只读。
    policy_source_db: str = "bid_analyse"
    # 调 ai-service 用上线模板跑批、调 codebook-service 取码表，都走对方的 /internal/ 接口。
    ai_base_url: str = "http://ai-service:8005"
    ai_service_secret: str = ""
    codebook_base_url: str = "http://codebook-service:8003"
    codebook_service_secret: str = ""
    internal_timeout_seconds: float = 30.0

    @model_validator(mode="after")
    def _reject_demo_secrets_in_production(self) -> Settings:
        if self.environment == Environment.PRODUCTION:
            markers = ("dev-", "example", "changeme", "test-secret", "p6-only")
            internal = (self.ai_service_secret, self.codebook_service_secret)
            for token in (self.iam_service_secret, self.audit_ingest_secret, *internal):
                if token and any(marker in token.lower() for marker in markers):
                    raise ValueError("生产环境内部调用密钥看起来是示例值，拒绝启动")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 必填项从环境变量读取，mypy 只看到构造参数缺失
