import { requestRetag, type AiTaskCode } from '@/api/aiTagging'

/**
 * 重新打标：把这些政策放回某个打标任务的待办，不当场调模型。列表页勾选多条、核对页对当前这条都走这里，
 * 结果交给 BatchChoiceDialog 显示（有跳过的逐条说原因）。
 */
export async function submitRetag(ids: string[], step: string): Promise<{ message: string; skipped: { reason: string; count: number }[] }> {
  const result = await requestRetag(ids, step as AiTaskCode)
  const message = result.queued
    ? `已把 ${result.queued} 条放回「${result.task}」的待办，到任务调度执行它或等每日计划`
    : '没有可以重新打标的政策'
  return { message, skipped: result.skipped }
}
