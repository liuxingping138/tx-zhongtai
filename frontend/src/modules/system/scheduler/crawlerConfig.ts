import type { ScheduledRun } from '@/api/scheduler'

/** 爬虫配置同步的任务编码，和 policy-service 的 app.crawlconfig.domain.models.JOB_CODE 一致。 */
export const CRAWLER_CONFIG_JOB = 'crawler_config'

/** 一次配置同步的结果写成一句话；还没有结果（排队、失败）返回空串。 */
export function configResultText(result: ScheduledRun['result']): string {
  if (result?.marked === undefined) return ''
  const added = result.added ? ` · 按栏目展开新增 ${result.added} 行` : ''
  const redated = result.redated ? ` · 上线时间对齐规则创建日期 ${result.redated} 个` : ''
  const unknown = result.unknown_codes ? `，${result.unknown_codes} 个信源表里没有` : ''
  const blank = result.blank_code_rows ? ` · ${result.blank_code_rows} 行没填网站编码` : ''
  return `新标已爬 ${result.marked} 个${added}${redated} · 规则表网站编码 ${result.rule_codes ?? 0} 个${unknown}${blank}${skippedText(result)}`
}

/** 没展开的规则：本周配置数比规则表新增条数少时，看这里知道差在哪。 */
function skippedText(result: NonNullable<ScheduledRun['result']>): string {
  const parts = [
    result.moved ? `${result.moved} 条规则展开后改了网站编码（已展开的行留在原编码下，请核对）` : '',
    result.conflicts ? `${result.conflicts} 条栏目名和已有信源重复没展开` : '',
    result.duplicates ? `${result.duplicates} 条同一网页已在另一编码下没展开` : '',
  ].filter(Boolean)
  return parts.length ? ` · ${parts.join('，')}` : ''
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
