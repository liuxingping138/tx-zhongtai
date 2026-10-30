/** 政策 AI 打标三个任务在任务调度页上的文案、写入量和金额格式。 */
import type { AiTaskCode } from '@/api/aiTagging'
import type { AiTaggingResult } from '@/api/scheduler'

const PREFIX = 'policy_ai_'
const CODES: AiTaskCode[] = ['type', 'interpret', 'opportunity']

/** 任务调度编码 -> 打标任务；不是打标任务返回 null。 */
export function taskOfJob(jobCode: string): AiTaskCode | null {
  const task = jobCode.startsWith(PREFIX) ? jobCode.slice(PREFIX.length) : ''
  return (CODES as string[]).includes(task) ? (task as AiTaskCode) : null
}

/** 每个任务做什么，设置抽屉和立即执行的确认里用。 */
export const TASK_INTRO: Record<AiTaskCode, string> = {
  type: '从读取进度往后读一批源政策，判断政策类型写入「政策基础标签」，信息化建设类标为需要解读。',
  interpret: '对基础标签里「是否解读 = 是」、还没解读的政策逐条解读，一条政策展开成多行写入「政策解读」。',
  opportunity: '对解读过、还没补市场机会的政策写市场机会，按一级行业 + 一级场景回填到它的解读行。',
}

/** 费用账单里这个任务的「用途」：政策服务发起批量任务时报的发起方名字。 */
export const TASK_PURPOSE: Record<AiTaskCode, string> = {
  type: '政策AI打标·类型判断',
  interpret: '政策AI打标·政策解读',
  opportunity: '政策AI打标·市场机会',
}

/** 执行记录「结果」列：失败写原因，成功写说明和花费。 */
export function runResultText(result: Partial<AiTaggingResult> | null | undefined): string {
  if (!result) return '—'
  if (result.error_message) return result.error_message
  const cost = Number(result.cost ?? 0) ? ` · ${formatYuan(result.cost)}` : ''
  return `${result.note || '—'}${cost}`
}

/** 费用到分；不足一分的小额（试跑几条）保留 4 位，免得显示成 ¥0.00。 */
export function formatYuan(value: string | number | null | undefined): string {
  const amount = Number(value ?? 0)
  if (!Number.isFinite(amount)) return '—'
  return `¥${amount !== 0 && Math.abs(amount) < 0.01 ? amount.toFixed(4) : amount.toFixed(2)}`
}

/** 设置里提交的起始采集日期：和打开时一样（没改）就发空串，后端不动读取进度。
 * 抽屉开着时一批跑完、进度已前移，把打开时的旧日期原样发回去会把进度退回那天第一条。 */
export function cursorToSend(current: string, opened: string): string {
  return current === opened ? '' : current
}
