import { http, request } from './http'
import type { Page } from './types'

export interface ScheduledRun {
  id: string; job_code: string; trigger: 'manual' | 'scheduled'; actor_name: string
  status: 'queued' | 'running' | 'retrying' | 'success' | 'failed' | 'cancelled'
  attempts: number; created_at: string; scheduled_at: string; available_at: string
  started_at: string | null; finished_at: string | null; error_message: string | null
  result: { date_from?: string; date_to?: string; watermark?: string; days_synced?: number;
    task_rows?: number; stat_rows?: number; health_rows?: number; site_rows?: number } | null
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
