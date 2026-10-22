import { http, request } from './http'
import type { Page } from './types'

export interface ScheduledRun {
  id: string; job_code: string; trigger: 'manual' | 'scheduled'; actor_name: string
  status: 'queued' | 'running' | 'retrying' | 'success' | 'failed' | 'cancelled'
  attempts: number; created_at: string; scheduled_at: string; available_at: string
  started_at: string | null; finished_at: string | null; error_message: string | null
  result: (CrawlerResult & Partial<AiTaggingResult>) | null
}
/** 爬虫增量同步的结果摘要 */
export interface CrawlerResult { date_from?: string; date_to?: string; watermark?: string; days_synced?: number; site_rows?: number }
/** 政策 AI 打标一批的结果摘要（也是调度页「政策 AI 打标」面板的一行） */
export interface AiTaggingResult {
  status: string; stage: string; source_from: string; source_to: string; source_rows: number
  tagged_rows: number; type_failed: number; interpret_rows: number; interpret_failed: number
  type_run_id: string; interpret_run_id: string; opportunity_run_id: string
  cost: string; note: string; error_message: string
}
export interface ScheduledJob {
  code: string; name: string; enabled: boolean; daily_time: string; next_run_at: string | null
  version: number; watermark: string | null; active_run: ScheduledRun | null; last_run: ScheduledRun | null
}
export interface SchedulerOverview {
  items: ScheduledJob[]; timezone: string; worker_online: boolean; heartbeat_at: string | null
}
const base = '/policy/scheduled-jobs'
export const listJobs = () => request<SchedulerOverview>(http.get(base))
export const updateJob = (code: string, payload: { enabled: boolean; daily_time: string; version: number }) =>
  request(http.patch(`${base}/${code}`, payload))
export const triggerJob = (code: string) => request<ScheduledRun>(http.post(`${base}/${code}/runs`))
export const listRuns = (code: string, page: number) =>
  request<Page<ScheduledRun>>(http.get(`${base}/${code}/runs`, { params: { page, page_size: 20 } }))
