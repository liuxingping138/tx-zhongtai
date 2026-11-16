import { requestRetag, type AiTaskCode } from '@/api/aiTagging'
import { triggerJob } from '@/api/scheduler'

/**
 * 重新打标：把这些政策放回某个打标任务的待办，并自动触发该任务的后台执行（若未在跑）。
 * 列表页勾选多条、核对页对当前这条都走这里，结果交给 BatchChoiceDialog 显示（有跳过的逐条说原因）。
 */
export async function submitRetag(ids: string[], step: string): Promise<{ message: string; skipped: { reason: string; count: number }[] }> {
  const result = await requestRetag(ids, step as AiTaskCode)
  if (!result.queued) {
    return { message: '没有可以重新打标的政策', skipped: result.skipped }
  }
  const triggered = await triggerJob(`policy_ai_${step}`, { base: '/policy' }).then(() => true, () => false)
  const message = triggered
    ? `已将 ${result.queued} 条加入「${result.task}」并立即启动后台重打，稍候自动更新结果`
    : `已把 ${result.queued} 条放回「${result.task}」的待办，到任务调度执行它或等每日计划`
  return { message, skipped: result.skipped }
}
