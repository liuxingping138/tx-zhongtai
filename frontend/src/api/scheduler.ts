import { http, request } from './http'
import { mergeOverviews } from './schedulerOverview'
import type { Page } from './types'

export interface ScheduledRun {
  id: string; job_code: string; trigger: 'manual' | 'scheduled'; actor_name: string
  status: 'queued' | 'running' | 'retrying' | 'success' | 'failed' | 'cancelled'
  attempts: number; created_at: string; scheduled_at: string; available_at: string
  started_at: string | null; finished_at: string | null; error_message: string | null
  result: (CrawlerResult & Partial<AiTaggingResult> & Partial<CrawlerConfigResult> & Partial<SessionCleanupResult>) | null
}
/** 爬虫增量同步的结果摘要 */
export interface CrawlerResult { date_from?: string; date_to?: string; watermark?: string; days_synced?: number; site_rows?: number }
/** 爬虫配置同步的结果摘要：规则表多少行、多少个网站编码，关联上多少信源、这次新标已爬多少个。 */
export interface CrawlerConfigResult {
  status: string; rule_rows: number; rule_codes: number; blank_code_rows: number
  matched: number; marked: number; redated: number; unknown_codes: number
  /** 按栏目展开新增的信源行数（规则表一行一个栏目，信源表跟着展开） */
  added?: number
}
/** IAM 清理失效会话的结果：删了多少、还剩多少、保留期多少天。 */
export interface SessionCleanupResult {
  retention_days: number; tokens_deleted: number; sessions_deleted: number; tokens_remaining: number; sessions_remaining: number
}
/** 政策 AI 打标一批的结果摘要。task 是三个打标任务之一；source_rows 是这一批处理的政策条数。 */
export interface AiTaggingResult {
  task: string; status: string; stage: string; source_from: string; source_to: string; source_rows: number
  tagged_rows: number; type_failed: number; interpret_rows: number; interpret_failed: number
  opportunity_rows: number; opportunity_failed: number
  type_run_id: string; interpret_run_id: string; opportunity_run_id: string
  cost: string; type_cost: string; interpret_cost: string; opportunity_cost: string
  note: string; error_message: string
}
export interface ScheduledJob {
  code: string; name: string; enabled: boolean; daily_time: string; next_run_at: string | null
  version: number; watermark: string | null; active_run: ScheduledRun | null; last_run: ScheduledRun | null
  /** 会花钱的任务：启用、改设置、立即执行还要这个资源可管理（如政策AI打标）。 */
  cost_resource?: string | null
  /** 前端补上的：任务所属服务的调度接口前缀，改计划、执行、看记录都发往这里。 */
  base: string
}
/** 一个服务的调度接口返回。 */
export interface ServiceOverview {
  items: Omit<ScheduledJob, 'base'>[]; timezone: string; worker_online: boolean; heartbeat_at: string | null
}
/**
 * 平台的定时任务分散在各服务里（各自的库和执行进程），调度页把它们汇总成一张表。
 * 新服务接入公共调度引擎后在这里加一行；顺序就是页面上的顺序。
 */
export const SCHEDULER_SERVICES = [
  { name: '政策服务', base: '/policy/scheduled-jobs' },
  { name: '系统管理', base: '/system/scheduled-jobs' },
] as const
export interface WorkerStatus { service: string; online: boolean; heartbeat_at: string | null; error: string }
export interface SchedulerOverview { items: ScheduledJob[]; workers: WorkerStatus[] }

const POLICY = SCHEDULER_SERVICES[0].base
/** 汇总各服务的任务；某个服务取不到时用 describe 把原因写成中文。 */
export const listJobs = async (describe: (cause: unknown) => string = String) =>
  mergeOverviews(
    SCHEDULER_SERVICES,
    await Promise.allSettled(SCHEDULER_SERVICES.map(({ base }) => request<ServiceOverview>(http.get(base)))),
    describe,
  )
/** 发往哪个服务由 listJobs 带回的 job.base 决定，调用方传 { base: job.base }。 */
interface Target { base?: string }
export const updateJob = (
  code: string, payload: { enabled: boolean; daily_time: string; version: number }, { base = POLICY }: Target = {},
) => request(http.patch(`${base}/${code}`, payload))
export const triggerJob = (code: string, { base = POLICY }: Target = {}) => request<ScheduledRun>(http.post(`${base}/${code}/runs`))
export const listRuns = (code: string, page: number, { base = POLICY }: Target = {}) =>
  request<Page<ScheduledRun>>(http.get(`${base}/${code}/runs`, { params: { page, page_size: 20 } }))
