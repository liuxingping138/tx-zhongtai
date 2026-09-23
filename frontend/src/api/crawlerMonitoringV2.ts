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

export interface CrawlerV2Overview {
  cards: { sites: number; normal: number; watch: number; stale: number; total_rows: number; yesterday_rows: number }
  sync: {
    status: '' | 'running' | 'success' | 'failed' | 'interrupted'
    started_at: string
    last_success_at: string
    outdated: boolean
  }
  thresholds: { normal_days: number; watch_days: number }
}

export interface CrawlerSiteFilters {
  province_name?: FilterParam
  city_name?: FilterParam
  site_name?: FilterParam
  status?: SiteStatus[]
}

export const CRAWLER_V2_BASE = '/policy/crawler-monitoring-v2'

export function getCrawlerV2Overview(): Promise<CrawlerV2Overview> {
  return request(http.get(`${CRAWLER_V2_BASE}/overview`))
}

export function listCrawlerSites(
  params: CrawlerSiteFilters & { page?: number; page_size?: number },
): Promise<Page<CrawlerSiteItem>> {
  return request(http.get(`${CRAWLER_V2_BASE}/sites`, { params }))
}
