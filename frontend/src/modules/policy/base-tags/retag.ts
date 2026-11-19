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
  const triggered = await triggerJob(`policy_ai_${step}`).then(() => true, () => false)
  const message = triggered
    ? `已将 ${result.queued} 条加入「${result.task}」并立即启动后台重打，稍候自动更新结果`
    : `已把 ${result.queued} 条放回「${result.task}」的待办，到任务调度执行它或等每日计划`
  return { message, skipped: result.skipped }
}

const MAX_POLL_TICKS = 30

function delayForTick(tickNumber: number): number {
  if (tickNumber <= 10) return 3000
  if (tickNumber <= 20) return 5000
  return 10000
}

/** 列表页批量重新打标后的后台轮询：采用退避间隔轮询目标行的版本/更新时间或状态变化，完成后按结果弹提示。 */
export function useListRetagPoll<T extends { id: string; version: number; updated_at?: string; tagged_at?: string; ai_status?: string }>(
  items: Ref<T[]>,
  refresh: () => Promise<void>,
) {
  const retagging = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let inFlight = false
  let disposed = false
  let runId = 0
  let trackedIds = new Set<string>()

  function stop() {
    runId += 1
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    attempt = 0
    inFlight = false
    retagging.value = false
  }

  function targetRows(rows: T[]): T[] {
    return trackedIds.size > 0 ? rows.filter(r => trackedIds.has(r.id)) : rows
  }

  function snapshot(rows: T[]): string | null {
    const relevant = targetRows(rows)
    if (trackedIds.size > 0 && relevant.length === 0) return null
    return relevant.map(r => `${r.id}:${r.version}:${r.updated_at ?? ''}:${r.tagged_at ?? ''}:${r.ai_status ?? ''}`).join('|')
  }

  function notifyFinished(rows: T[]) {
    const hasFailure = targetRows(rows).some(r => r.ai_status?.includes('失败'))
    if (hasFailure) {
      ElMessage.warning('重新打标结束，部分条目失败，请查看状态')
      return
    }
    ElMessage.success('重新打标已完成，列表数据已自动更新')
  }

  function tryComplete(baseline: string | null): boolean {
    const current = snapshot(items.value)
    if (current === null || baseline === null || current === baseline) return false
    stop()
    notifyFinished(items.value)
    return true
  }

  function scheduleNext(baseline: string | null, myRun: number) {
    if (disposed || !retagging.value || myRun !== runId) return
    attempt += 1
    if (attempt > MAX_POLL_TICKS) {
      stop()
      ElMessage.info('后台仍在重新打标，稍后可手动刷新查看结果')
      return
    }
    timer = setTimeout(() => {
      timer = null
      void tick(baseline, myRun)
    }, delayForTick(attempt))
  }

  async function tick(baseline: string | null, myRun: number) {
    if (inFlight || disposed || myRun !== runId) return
    inFlight = true
    try {
      await refresh()
      if (!disposed && myRun === runId) tryComplete(baseline)
    } finally {
      inFlight = false
      if (myRun === runId) scheduleNext(baseline, myRun)
    }
  }

  async function startAfterRetag(targetIds?: string[]) {
    stop()
    const myRun = runId
    trackedIds = new Set(targetIds ?? [])
    await refresh()
    if (disposed || myRun !== runId) return
    const baseline = snapshot(items.value)
    retagging.value = true
    attempt = 0
    scheduleNext(baseline, myRun)
  }

  onBeforeUnmount(() => {
    disposed = true
    stop()
  })
  return { retagging, startAfterRetag, stop }
}
