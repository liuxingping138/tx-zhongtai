import type { ScheduledRun } from '@/api/scheduler'

export type RunStatus = ScheduledRun['status']

export const STATUS_TEXT: Record<RunStatus, string> = {
  queued: '排队中',
  running: '运行中',
  retrying: '等待重试',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
}

/** 状态标签颜色：成功绿、失败红、等待重试橙，其余灰。 */
export function statusType(status?: RunStatus): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'retrying') return 'warning'
  return 'info'
}

/** 一次执行从开始到结束花了多久；还没开始或没结束显示「—」。 */
export function duration(row: Pick<ScheduledRun, 'started_at' | 'finished_at'>): string {
  if (!row.started_at || !row.finished_at) return '—'
  const seconds = Math.max(0, Math.round((Date.parse(row.finished_at) - Date.parse(row.started_at)) / 1000))
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}

/** 最近一次失败时的原因摘要。 */
export function lastFailureReason(run?: ScheduledRun | null): string {
  return run?.status === 'failed' ? run.error_message || '' : ''
}
