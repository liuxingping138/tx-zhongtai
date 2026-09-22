import { http, request } from './http'
import type { Page } from './types'

export type HealthStatus = 'normal' | 'watch' | 'broken' | 'never'

export interface CrawlerTaskItem {
  id: string
  site_code: string
  site_name: string
  province_name: string
  city_name: string
  tag: string
  source_url: string
  last_collect_date: string
  stale_days: number | null
  count_7d: number
  count_30d: number
  count_90d: number
  count_total: number
  health_status: HealthStatus
  health_status_label: string
  in_rules: boolean
  in_rules_label: string
  computed_at: string
}

export interface CrawlerOverview {
  cards: {
    yesterday_rows: number
    yesterday_rows_delta: number
    yesterday_sites: number
    total_tasks: number
    abnormal_tasks: number
    healthy_ratio: number
    sites_total: number
    sites_all_broken: number
    sites_partial_broken: number
  }
  health_distribution: { status: HealthStatus; label: string; count: number }[]
  trend: { date: string; rows: number; sites: number }[]
  last_sync: { status: string; finished_at: string; date_to: string; error_message: string | null } | null
}

export interface CrawlerTaskFilters {
  province_name?: string
  city_name?: string
  site_name?: string
  site_code?: string
  tag?: string
  health_status?: string
  stale_days_min?: number
  abnormal_only?: boolean
}

export function getCrawlerOverview(trendDays = 30): Promise<CrawlerOverview> {
  return request(http.get('/policy/crawler-monitoring/overview', { params: { trend_days: trendDays } }))
}

export function listCrawlerTasks(
  params: CrawlerTaskFilters & { page?: number; page_size?: number },
): Promise<Page<CrawlerTaskItem>> {
  return request(http.get('/policy/crawler-monitoring/tasks', { params }))
}

export function getCrawlerTaskDetail(params: {
  site_code: string
  tag: string
  days?: number
}): Promise<{ task: CrawlerTaskItem; series: { date: string; rows: number }[] }> {
  return request(http.get('/policy/crawler-monitoring/tasks/detail', { params }))
}
