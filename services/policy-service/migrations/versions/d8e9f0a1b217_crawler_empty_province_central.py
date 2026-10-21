"""爬虫监测：省份为空的网站并入「国央企」，与同名同地市的国央企网站合并

Revision ID: d8e9f0a1b217
Revises: c4e7a2d9f318
"""

from alembic import op

revision = "d8e9f0a1b217"
down_revision = "c4e7a2d9f318"
branch_labels = None
depends_on = None

# 与 app.crawler.domain.provinces.EMPTY_PROVINCE_CATEGORY 一致；迁移不 import 运行时模块。
CENTRAL = "国央企"


def upgrade() -> None:
    # 按天统计：同一天同一网站两种写法都有时，条数相加、时间取较新的。GREATEST 忽略 NULL。
    op.execute(
        f"""INSERT INTO policy_crawler_site_daily AS t (
            collect_date, site_name, province_name, city_name, row_count, last_created_at, last_published_date, synced_at
        )
        SELECT collect_date, site_name, '{CENTRAL}', city_name, row_count, last_created_at, last_published_date, synced_at
        FROM policy_crawler_site_daily WHERE province_name = ''
        ON CONFLICT (collect_date, site_name, province_name, city_name) DO UPDATE SET
            row_count = t.row_count + EXCLUDED.row_count,
            last_created_at = GREATEST(t.last_created_at, EXCLUDED.last_created_at),
            last_published_date = GREATEST(t.last_published_date, EXCLUDED.last_published_date),
            synced_at = GREATEST(t.synced_at, EXCLUDED.synced_at)"""
    )
    op.execute("DELETE FROM policy_crawler_site_daily WHERE province_name = ''")
    # 快照：有同名国央企网站的合并过去（停更天数取较少的那条及其状态），其余直接改写省份。
    op.execute(
        f"""UPDATE policy_crawler_sites AS t SET
            total_rows = t.total_rows + e.total_rows,
            last_created_at = GREATEST(t.last_created_at, e.last_created_at),
            last_published_date = GREATEST(t.last_published_date, e.last_published_date),
            stale_days = LEAST(t.stale_days, e.stale_days),
            status = CASE WHEN e.stale_days IS NOT NULL AND (t.stale_days IS NULL OR e.stale_days < t.stale_days)
                          THEN e.status ELSE t.status END
        FROM policy_crawler_sites AS e
        WHERE e.province_name = '' AND t.province_name = '{CENTRAL}'
          AND t.site_name = e.site_name AND t.city_name = e.city_name"""
    )
    op.execute(
        f"""DELETE FROM policy_crawler_sites AS e USING policy_crawler_sites AS t
        WHERE e.province_name = '' AND t.province_name = '{CENTRAL}'
          AND t.site_name = e.site_name AND t.city_name = e.city_name"""
    )
    op.execute(f"UPDATE policy_crawler_sites SET province_name = '{CENTRAL}' WHERE province_name = ''")


def downgrade() -> None:
    # 合并后分不出哪些行原本省份为空，不能无损回退。
    raise RuntimeError("空省份并入国央企不能无损回退，请恢复迁移前备份。")
