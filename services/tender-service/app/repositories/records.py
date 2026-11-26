"""原始和交付数据按状态切换；列表从不读取 content 大字段。"""

from datetime import date, timedelta

from app.core.source import Reader, Row
from app.domain.fields import REGION_FIELDS, TABLES, Kind, Status, columns
from app.domain.queries import MAX_ROUTED_DAYS, ListQuery

QLM_ID_MAX_LENGTH = 13


def where_clause(query: ListQuery) -> tuple[str, tuple[object, ...]]:
    clauses: list[str] = []
    values: list[object] = []
    if query.project_status and query.project_status != "all":
        clauses.append("project_status = %s")
        values.append(query.project_status)
    if query.project_name.strip():
        # 使用 = 作为转义字符，避免关键词中的 %、_ 变成通配符。
        keyword = query.project_name.strip().replace("=", "==").replace("%", "=%").replace("_", "=_")
        clauses.append("project_name LIKE %s ESCAPE '='")
        values.append(f"%{keyword}%")
    if query.project_content_id.strip():
        clauses.append("project_content_id = %s")
        values.append(query.project_content_id.strip())
    for field in (*REGION_FIELDS, "is_supp_scene"):
        selected = getattr(query, field)
        if selected:
            clauses.append(f"{field} IN ({', '.join(['%s'] * len(selected))})")
            values.extend(selected)
    for field in ("collect_date", "public_date", "create_time"):
        parts, dates = date_conditions(field, getattr(query, f"{field}_from"), getattr(query, f"{field}_to"))
        clauses.extend(parts)
        values.extend(dates)
    return " AND ".join(clauses) if clauses else "1=1", tuple(values)


def date_conditions(field: str, start: date | None, end: date | None) -> tuple[list[str], list[str]]:
    # collect_date 是 YYYY-MM-DD 采集日。分片代理对 >=/< 的路由会全表扫描，
    # 有界日期枚举成等值/IN 才能精确落到分片；一年以上不生成超长 SQL。
    if field == "collect_date" and start and end and (end - start).days < MAX_ROUTED_DAYS:
        days = [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)]
        condition = "collect_date = %s" if len(days) == 1 else f"collect_date IN ({', '.join(['%s'] * len(days))})"
        return [condition], days
    clauses, values = [], []
    if start:
        clauses.append(f"{field} >= %s")
        values.append(start.isoformat())
    if end:
        clauses.append(f"{field} < %s")
        values.append((end + timedelta(days=1)).isoformat())
    return clauses, values


def order_clause(query: ListQuery) -> str:
    has_scope = bool(
        query.purchaser_provname
        or query.collect_date_from
        or query.collect_date_to
        or query.public_date_from
        or query.public_date_to
        or query.create_time_from
        or query.create_time_to
        or query.project_name.strip()
        or query.project_content_id.strip()
    )
    if query.project_status == "1" or has_scope:
        return "ORDER BY public_date DESC, purchaser_provname DESC, id DESC"
    return "ORDER BY public_date DESC, id DESC"


def count_records(reader: Reader, kind: Kind, query: ListQuery) -> int:
    table = TABLES[kind, query.project_status]
    where, params = where_clause(query)
    sql = f"SELECT COUNT(*) AS total FROM {table} WHERE {where}"  # noqa: S608  标识符来自白名单，值绑定参数
    return int(reader.select(sql, params)[0]["total"])


def list_records(reader: Reader, kind: Kind, query: ListQuery) -> list[Row]:
    table = TABLES[kind, query.project_status]
    where, params = where_clause(query)
    order = order_clause(query)
    sql = (
        f"SELECT {', '.join(columns(kind))} FROM {table} "  # noqa: S608  标识符来自白名单，值绑定参数
        f"WHERE {where} {order} LIMIT %s OFFSET %s"
    )
    return reader.select(sql, (*params, query.page_size + 1, (query.page - 1) * query.page_size))


def export_records(reader: Reader, kind: Kind, query: ListQuery, *, limit: int) -> list[Row]:
    table = TABLES[kind, query.project_status]
    where, params = where_clause(query)
    order = order_clause(query)
    sql = (
        f"SELECT {', '.join(columns(kind))} FROM {table} "  # noqa: S608  标识符来自白名单，值绑定参数
        f"WHERE {where} {order} LIMIT %s"
    )
    return reader.select(sql, (*params, limit + 1))


def get_record(reader: Reader, kind: Kind, status: Status, record_id: int) -> Row | None:
    cols = ", ".join(columns(kind))
    use_status = status and status != "all"
    table = TABLES[kind, status] if use_status else TABLES[kind, "0"]
    cond = "id = %s AND project_status = %s" if use_status else "id = %s"
    params = (record_id, status) if use_status else (record_id,)
    sql = f"SELECT {cols} FROM {table} WHERE {cond} LIMIT 1"  # noqa: S608  白名单表名列名，值参数化
    rows = reader.select(sql, params)
    return rows[0] if rows else None


def original_reference(reader: Reader, kind: Kind, row: Row) -> Row | None:
    content_id = str(row.get("project_content_id") or "").strip()
    if not content_id:
        return None
    rows = reader.select(
        f"SELECT project_content_id, collect_date FROM {TABLES[kind, '0']} "  # noqa: S608  表名和列名来自固定白名单，筛选值全部绑定参数
        "WHERE project_content_id = %s ORDER BY collect_date DESC, id DESC LIMIT 1",
        (content_id,),
    )
    return rows[0] if rows else None


def read_content(reader: Reader, reference: Row) -> Row | None:
    content_id = str(reference.get("project_content_id") or "")
    if not content_id:
        return None
    if len(content_id) <= QLM_ID_MAX_LENGTH:
        # 先校验数字，避免 MySQL 把非数字 ID 隐式转换为 0 或错误命中数字前缀。
        if not content_id.isascii() or not content_id.isdecimal():
            return None
        rows = reader.select(
            "SELECT infocontent AS html FROM bid_analyse.qlm_saas_content WHERE infoid = %s LIMIT 1",
            (int(content_id),),
        )
    elif reference.get("collect_date"):
        rows = reader.select(
            "SELECT content AS html FROM crawler2021.zhaobiao2021_prod WHERE uid = %s AND create_time = %s LIMIT 1",
            (content_id, reference["collect_date"]),
        )
    else:
        return None
    return rows[0] if rows else None
