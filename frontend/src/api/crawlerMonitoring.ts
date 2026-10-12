import { http, request } from './http'
import type { FilterParam, Page } from './types'

export type SiteStatus = 'normal' | 'watch' | 'stale'

export interface CrawlerSiteItem {
  id: string
  site_name: string
  province_name: string
  city_name: string
  total_rows: number
  last_created_at: string
  last_published_date: string
  stale_days: number | null
  status: SiteStatus
  status_label: string
}

export interface CrawlerHealth {
  normal: number
  watch: number
  /** 停更但未超过 long_stale_days，多半是爬虫或网站近期出了问题。 */
  stale_recent: number
  /** 超过 long_stale_days 没有新数据，多半是网站下线或改版。 */
  stale_long: number
  long_stale_days: number
}

export interface CrawlerProvince {
  /** 图表里合并后的省份名。 */
  name: string
  /** 合并前的原始写法，点击后按它们筛选表格。 */
  raw_names: string[]
  normal: number
  watch: number
  stale: number
  sites: number
}

export interface CrawlerTrendPoint {
  date: string
  rows: number
  sites: number
}

export type CrawlerTrendDays = 7 | 30 | 90 | 365

export interface CrawlerOverviewData {
  cards: { sites: number; normal: number; watch: number; stale: number; total_rows: number }
  /** 截至昨日的近 N 天采集条数和再往前 N 天的条数。 */
  recent: { days: number; rows: number; previous_rows: number }
  /** 一周前的状态分布，用于「较上周」；还没有那天的记录时为 null。 */
  week_base: { date: string; sites: number; normal: number; watch: number; stale: number } | null
  health: CrawlerHealth
  /** 「省份」字段的全部分类：32 个省级行政区、香港、澳门、全国、国央企，以及未填等。 */
  provinces: CrawlerProvince[]
  sync: {
    status: '' | 'running' | 'success' | 'failed' | 'interrupted'
    started_at: string
    last_success_at: string
    outdated: boolean
  }
  thresholds: { normal_days: number; watch_days: number }
}

export interface CrawlerSiteRef {
  site_name: string
  province_name: string
  city_name: string
}

export interface CrawlerSiteFilters {
  province_name?: FilterParam
  city_name?: FilterParam
  site_name?: FilterParam
  status?: SiteStatus[]
}

export const CRAWLER_BASE = '/policy/crawler-monitoring'

export function getCrawlerOverview(): Promise<CrawlerOverviewData> {
  return request(http.get(`${CRAWLER_BASE}/overview`))
}

export function getCrawlerTrend(
  days: CrawlerTrendDays,
): Promise<{ date_from: string; date_to: string; items: CrawlerTrendPoint[] }> {
  return request(http.get(`${CRAWLER_BASE}/trend`, { params: { days } }))
}

export function getCrawlerSiteTrend(
  site: CrawlerSiteRef,
  days: CrawlerTrendDays,
): Promise<{ date_from: string; date_to: string; items: CrawlerTrendPoint[] }> {
  return request(http.get(`${CRAWLER_BASE}/site-trend`, { params: { ...site, days } }))
}

export function listCrawlerSites(
  params: CrawlerSiteFilters & { page?: number; page_size?: number },
): Promise<Page<CrawlerSiteItem>> {
  return request(http.get(`${CRAWLER_BASE}/sites`, { params }))
}
