"""P6 爬虫页面端到端测试数据：纯本地快照，不连接真实 MySQL 源库。"""
import asyncio
from datetime import timedelta

from platform_common.clock import utcnow
from sqlalchemy import delete

from app.core.database import SessionLocal, engine
from app.crawler.domain.models import CrawlerSite, CrawlerSiteDaily, CrawlerV2SyncRun


async def main():
    assert engine.url.database == 'policy_p6_db', '只允许在 policy_p6_db 建立验收数据'
    now = utcnow()
    today = now.date()
    async with SessionLocal() as session:
        for model in (CrawlerSiteDaily, CrawlerSite, CrawlerV2SyncRun):
            await session.execute(delete(model))
        for i in range(60):
            name=f'P6验收网站{i:03d}'
            province=['海南省','甘肃省','广东省'][i%3]
            stale=[1,15,45][i%3]
            last=today-timedelta(days=stale)
            session.add(CrawlerSite(site_name=name,province_name=province,city_name='验收地市',
                total_rows=10,last_created_at=now-timedelta(days=stale),last_published_date=last,
                stale_days=stale,status=['normal','watch','stale'][i%3],computed_at=now))
            session.add(CrawlerSiteDaily(collect_date=last,site_name=name,province_name=province,
                city_name='验收地市',row_count=10,last_created_at=now-timedelta(days=stale),
                last_published_date=last,synced_at=now))
        session.add(CrawlerV2SyncRun(mode='backfill',started_at=now,finished_at=now,date_from=today-timedelta(days=90),
            date_to=today,days_synced=90,site_rows=60,status='success',watermark=now))
        await session.commit()
    await engine.dispose()
    print('p6_crawler_fixtures_ready')


asyncio.run(main())
