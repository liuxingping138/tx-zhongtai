import type { ScheduledRun } from '@/api/scheduler'

/** IAM 清理失效会话的任务编码，和 iam-service 的 app.application.scheduled_jobs.SESSION_CLEANUP 一致。 */
export const SESSION_CLEANUP_JOB = 'iam_session_cleanup'

/** 一次清理的结果写成一句话；还没有结果（排队、失败）返回空串。 */
export function cleanupResultText(result: ScheduledRun['result']): string {
  if (result?.sessions_deleted === undefined) return ''
  return `删除失效会话 ${result.sessions_deleted} 个、刷新令牌 ${result.tokens_deleted ?? 0} 个 · 保留 ${result.retention_days ?? '—'} 天内的记录 · 剩余会话 ${result.sessions_remaining ?? '—'} 个`
}

/** 执行记录一行的结果：有结果写结果，失败写原因。 */
export function cleanupRunText(row: Pick<ScheduledRun, 'result' | 'error_message'>): string {
  return cleanupResultText(row.result) || row.error_message || '—'
}

/** 调度列表「数据进度」：上次清了多少个会话。 */
export function cleanupProgress(run: ScheduledRun | null): string {
  const deleted = run?.result?.sessions_deleted
  return deleted === undefined ? '—' : `上次清理 ${deleted} 个会话`
}
