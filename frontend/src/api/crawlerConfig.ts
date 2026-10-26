import { http, request } from './http'
import type { ScheduledRun } from './scheduler'

export type ConfigUnit = 'week' | 'month' | 'quarter' | 'year'
/** 信源表一个省的爬虫状态透视；total = 已爬 + 未爬 + 异常 + 状态为空的 */
export interface ConfigStatusRow { province_name: string; total: number; online: number; pending: number; abnormal: number }
export interface ConfigTotals extends Omit<ConfigStatusRow, 'province_name'> {
  /** 已爬占比，百分数，一位小数 */
  coverage: number
}
export interface ConfigPeriod { period_from: string; period_to: string; new: number }
export interface ConfigProvinceCount { province_name: string; new: number }
export interface ConfigSite {
  province_name: string; city_name: string; district_name: string; site_name: string
  site_code: string; url: string; crawler_status: string; online_date: string
}
export interface ConfigSyncSummary {
  status: string; rule_rows: number; rule_codes: number; blank_code_rows: number
  matched: number; marked: number; redated: number; unknown_codes: number; finished_at: string
}
export interface CrawlerConfigReport {
  unit: ConfigUnit
  /** 所选这期的第一天和最后一天 */
  period_from: string; period_to: string
  /** 今天所在这期的第一天：判断所选是「本周」还是「上周」 */
  current_from: string
  /** 所选这期配置了多少网站，上一期多少 */
  new: number; previous_new: number
  /** 柱图各期，从早到晚，最后一期是今天所在这期 */
  periods: ConfigPeriod[]
  /** 所选这期有配置的省份，按数量从多到少 */
  provinces: ConfigProvinceCount[]
  /** 信源表按省透视的爬虫状态，按省份编码排 */
  status: ConfigStatusRow[]
  totals: ConfigTotals
  /** 上线时统一补填上线时间的那天：这天上线的不知道真实配置日，算期初，不计入任何一期 */
  backfill_date: string
  /** 期初：补填日上线的加上已爬没填日期的 */
  baseline: number
  new_sites: ConfigSite[]
  last_sync: ConfigSyncSummary | null
}
export interface ConfigSyncStatus { active_run: ScheduledRun | null; last_run: ScheduledRun | null }

export const CRAWLER_CONFIG_BASE = '/policy/crawler-config'

/** period 是所选这期内任意一天（YYYY-MM-DD）；不传时周看上周，月、季度、年看当前这期。 */
export function getCrawlerConfigReport(unit: ConfigUnit, period?: string): Promise<CrawlerConfigReport> {
  return request(http.get(`${CRAWLER_CONFIG_BASE}/report`, { params: period ? { unit, period } : { unit } }))
}

export function getConfigSyncStatus(): Promise<ConfigSyncStatus> {
  return request(http.get(`${CRAWLER_CONFIG_BASE}/sync`))
}

/** 立即同步规则表：放进调度队列，由 policy-worker 执行。 */
export function triggerConfigSync(): Promise<ScheduledRun> {
  return request(http.post(`${CRAWLER_CONFIG_BASE}/sync`))
}
