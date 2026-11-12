"""所有统计仅取原始表，单天聚合避免跨分片全量 GROUP BY。"""

from datetime import date

from app.core.source import Reader, Row
from app.domain.fields import TABLES, Kind


def totals(reader: Reader, kind: Kind) -> int:
    return int(reader.select(f"SELECT COUNT(*) AS total FROM {TABLES[kind, '0']}")[0]["total"])  # noqa: S608  表名和列名来自固定白名单，筛选值全部绑定参数


def daily(reader: Reader, kind: Kind, day: date) -> list[Row]:
    return reader.select(
        "SELECT purchaser_provname AS province, COUNT(*) AS total, "  # noqa: S608  表名和列名来自固定白名单，筛选值全部绑定参数
        "SUM(CASE WHEN project_status = '1' THEN 1 ELSE 0 END) AS processed "
        f"FROM {TABLES[kind, '0']} WHERE collect_date = %s GROUP BY purchaser_provname",
        (day.isoformat(),),
    )
