import type { ScheduledRun } from '@/api/scheduler'

/** 审计服务清理到期操作日志的任务编码，和 audit-service 的 app.application.scheduled_jobs.AUDIT_CLEANUP 一致。 */
export const AUDIT_CLEANUP_JOB = 'audit_cleanup'

/** 一次清理的结果写成一句话；还没有结果（排队、失败）返回空串。这个任务真删审计记录，删了多少要写清楚。 */
export function auditCleanupResultText(result: ScheduledRun['result']): string {
  if (result?.deleted === undefined) return ''
  return `删除到期操作日志 ${result.deleted} 条 · 保留 ${result.retention_days ?? '—'} 天内的记录`
}

/** 执行记录一行的结果：有结果写结果，失败写原因。 */
export function auditCleanupRunText(row: Pick<ScheduledRun, 'result' | 'error_message'>): string {
  return auditCleanupResultText(row.result) || row.error_message || '—'
}

/** 调度列表「数据进度」：上次删了多少条。 */
export function auditCleanupProgress(run: ScheduledRun | null): string {
  const deleted = run?.result?.deleted
  return deleted === undefined ? '—' : `上次删除 ${deleted} 条`
}
