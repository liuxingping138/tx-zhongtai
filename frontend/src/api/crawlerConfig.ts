import { http, request } from './http'
import type { ScheduledRun } from './scheduler'

export interface ConfigCounts {
  total: number; online: number; pending: number; abnormal: number; new: number
  /** 已爬占比，百分数，一位小数 */
  coverage: number
}
export interface ConfigProvince extends ConfigCounts {
  province_name: string
  /** 和 trend 同样的几周里，这个省每周新配置的栏目数 */
  weekly: number[]
}
export interface ConfigWeek { week_from: string; week_to: string; new: number; cumulative: number }
export interface ConfigSite {
  province_name: string; city_name: string; district_name: string; site_name: string
  site_code: string; url: string; crawler_status: string; online_date: string
}
export interface ConfigSyncSummary {
  status: string; rule_rows: number; rule_codes: number; blank_code_rows: number
  matched: number; marked: number; unknown_codes: number; finished_at: string
}
export interface CrawlerConfigReport {
  week_from: string; week_to: string
  /** 统计起始周（周一）：之前上线的算期初存量 */
  report_start: string
  /** 所选周是否在统计范围内 */
  counted: boolean
  baseline: number
  /** 上周新增；上周不在统计范围内时为 null */
  previous_new: number | null
  totals: ConfigCounts
  provinces: ConfigProvince[]
  trend: ConfigWeek[]
  new_sites: ConfigSite[]
  last_sync: ConfigSyncSummary | null
}
export interface ConfigSyncStatus { active_run: ScheduledRun | null; last_run: ScheduledRun | null }

export const CRAWLER_CONFIG_BASE = '/policy/crawler-config'

/** week 是所选周内任意一天（YYYY-MM-DD），不传为本周。 */
export function getCrawlerConfigReport(week?: string): Promise<CrawlerConfigReport> {
  return request(http.get(`${CRAWLER_CONFIG_BASE}/report`, { params: week ? { week } : {} }))
}

export function getConfigSyncStatus(): Promise<ConfigSyncStatus> {
  return request(http.get(`${CRAWLER_CONFIG_BASE}/sync`))
}

/** 立即同步规则表：放进调度队列，由 policy-worker 执行。 */
export function triggerConfigSync(): Promise<ScheduledRun> {
  return request(http.post(`${CRAWLER_CONFIG_BASE}/sync`))
}
