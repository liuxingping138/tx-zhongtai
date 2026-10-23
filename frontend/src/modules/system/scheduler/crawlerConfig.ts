import type { ScheduledRun } from '@/api/scheduler'

/** 爬虫配置同步的任务编码，和 policy-service 的 app.crawlconfig.domain.models.JOB_CODE 一致。 */
export const CRAWLER_CONFIG_JOB = 'crawler_config'

/** 一次配置同步的结果写成一句话；还没有结果（排队、失败）返回空串。 */
export function configResultText(result: ScheduledRun['result']): string {
  if (result?.marked === undefined) return ''
  const unknown = result.unknown_codes ? `，${result.unknown_codes} 个信源表里没有` : ''
  const blank = result.blank_code_rows ? ` · ${result.blank_code_rows} 行没填网站编码` : ''
  return `新标已爬 ${result.marked} 个 · 规则表网站编码 ${result.rule_codes ?? 0} 个${unknown}${blank}`
}

/** 执行记录一行的结果：有结果写结果，失败写原因。 */
export function configRunText(row: Pick<ScheduledRun, 'result' | 'error_message'>): string {
  return configResultText(row.result) || row.error_message || '—'
}

/** 调度列表「数据进度」：上次同步新标了多少个已爬。 */
export function configProgress(run: ScheduledRun | null): string {
  const marked = run?.result?.marked
  return marked === undefined ? '—' : `上次新标已爬 ${marked} 个`
}
