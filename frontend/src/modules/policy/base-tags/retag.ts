import { onBeforeUnmount, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
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

/** 列表页批量重新打标后的后台轮询：一旦列表行的版本/更新时间或状态发生变化，立即停轮询并弹出完成通知。 */
export function useListRetagPoll<T extends { id: string; version: number; updated_at?: string; tagged_at?: string; ai_status?: string }>(
  items: Ref<T[]>,
  refresh: () => Promise<void>,
) {
  const retagging = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null
  let remaining = 0
  let inFlight = false
  let disposed = false

  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    remaining = 0
    inFlight = false
    retagging.value = false
  }

  function snapshot(rows: T[]): string {
    return rows.map(r => `${r.id}:${r.version}:${r.updated_at ?? ''}:${r.tagged_at ?? ''}:${r.ai_status ?? ''}`).join('|')
  }

  async function tick(baseline: string) {
    if (inFlight || disposed) return
    inFlight = true
    try {
      await refresh()
      if (disposed || !retagging.value) return
      if (snapshot(items.value) !== baseline) {
        stop()
        ElMessage.success('重新打标已完成，列表数据已自动更新')
      }
    } finally {
      inFlight = false
    }
  }

  async function startAfterRetag() {
    stop()
    await refresh()
    if (disposed) return
    const baseline = snapshot(items.value)
    retagging.value = true
    remaining = 30
    timer = setInterval(() => {
      remaining -= 1
      if (remaining <= 0) {
        stop()
        return
      }
      void tick(baseline)
    }, 3000)
  }

  onBeforeUnmount(() => {
    disposed = true
    stop()
  })
  return { retagging, startAfterRetag, stop }
}
