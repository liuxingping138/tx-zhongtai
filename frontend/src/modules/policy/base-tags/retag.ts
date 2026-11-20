import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { requestRetag, type AiTaskCode } from '@/api/aiTagging'
import { ApiRequestError } from '@/api/errors'
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

/** 约 15 分钟：前 10 次 3 秒、再 10 次 5 秒，之后每 10 秒一次。AI 一批常要好几分钟，3 分钟就放弃太早。 */
export const MAX_POLL_TICKS = 102
const FETCH_CHUNK = 10

function delayForTick(tickNumber: number): number {
  if (tickNumber <= 10) return 3000
  if (tickNumber <= 20) return 5000
  return 10000
}

type RetagRow = { id: string; version: number; updated_at?: string; tagged_at?: string; ai_status?: string }
/** 一行的打标结果：gone = 这一行已经没了（重新解读会换掉旧的解读行），算处理完。 */
type RowState = { gone: true } | { gone: false; key: string; failed: boolean }

function rowState(row: RetagRow): RowState {
  const key = `${row.version}:${row.updated_at ?? ''}:${row.tagged_at ?? ''}:${row.ai_status ?? ''}`
  return { gone: false, key, failed: Boolean(row.ai_status?.includes('失败')) }
}

/** 按 ID 取一行；404 是被换掉了，其他错误（网络抖动）返回 null，下次再问。 */
async function readRow<T extends RetagRow>(fetchRow: (id: string) => Promise<T>, id: string): Promise<RowState | null> {
  try {
    return rowState(await fetchRow(id))
  } catch (error) {
    return error instanceof ApiRequestError && error.status === 404 ? { gone: true } : null
  }
}

async function readRows<T extends RetagRow>(fetchRow: (id: string) => Promise<T>, ids: string[]): Promise<Map<string, RowState | null>> {
  const states = new Map<string, RowState | null>()
  for (let start = 0; start < ids.length; start += FETCH_CHUNK) {
    const chunk = ids.slice(start, start + FETCH_CHUNK)
    const read = await Promise.all(chunk.map((id) => readRow(fetchRow, id)))
    chunk.forEach((id, index) => states.set(id, read[index] ?? null))
  }
  return states
}

function finishedMessage(done: number, failed: number): string {
  return failed
    ? `重新打标结束：${done} 条已处理，其中 ${failed} 条失败，请按「打标状态」查看`
    : `重新打标已完成 ${done} 条，列表数据已自动更新`
}

/**
 * 列表页批量重新打标后的后台轮询：按 ID 逐条去问勾选的那几行（不看当前页，翻页、筛选都不影响），
 * 某一行的版本、打标时间或状态变了就算这一行处理完，行没了（重新解读换掉了旧解读行）也算；
 * 全部处理完才提示，失败的单独数出来。最多问约 15 分钟。
 */
export function useListRetagPoll<T extends RetagRow>(
  refresh: () => Promise<void>,
  fetchRow: (id: string) => Promise<T>,
) {
  const retagging = ref(false)
  const progress = ref({ done: 0, failed: 0, total: 0 })
  let timer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let disposed = false
  let runId = 0
  let baseline = new Map<string, string>()

  function stop() {
    runId += 1
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    attempt = 0
    retagging.value = false
  }

  /** 记下这一行的结果，返回它是不是处理完了。 */
  function settle(id: string, state: RowState | null): boolean {
    if (state === null) return false
    if (!state.gone && state.key === baseline.get(id)) return false
    baseline.delete(id)
    progress.value.done += 1
    if (!state.gone && state.failed) progress.value.failed += 1
    return true
  }

  async function safeRefresh() {
    await refresh().catch(() => undefined)
  }

  async function finish() {
    const { done, failed } = progress.value
    stop()
    const ended = runId
    await safeRefresh()
    if (disposed || ended !== runId) return
    if (failed) ElMessage.warning(finishedMessage(done, failed))
    else ElMessage.success(finishedMessage(done, failed))
  }

  async function giveUp() {
    const { done, total } = progress.value
    stop()
    const ended = runId
    await safeRefresh()
    if (disposed || ended !== runId) return
    ElMessage.info(`后台仍在重新打标（已处理 ${done} / ${total} 条），稍后可手动刷新查看结果`)
  }

  function scheduleNext(myRun: number) {
    if (disposed || myRun !== runId) return
    attempt += 1
    if (attempt > MAX_POLL_TICKS) {
      void giveUp()
      return
    }
    timer = setTimeout(() => {
      timer = null
      void tick(myRun)
    }, delayForTick(attempt))
  }

  async function tick(myRun: number) {
    const states = await readRows(fetchRow, [...baseline.keys()])
    if (disposed || myRun !== runId) return
    let changed = false
    for (const [id, state] of states) changed = settle(id, state) || changed
    if (baseline.size === 0) {
      await finish()
      return
    }
    if (changed) await safeRefresh()
    scheduleNext(myRun)
  }

  async function startAfterRetag(targetIds: string[]) {
    stop()
    const myRun = runId
    await safeRefresh()
    const states = await readRows(fetchRow, [...new Set(targetIds)])
    if (disposed || myRun !== runId) return
    baseline = new Map()
    for (const [id, state] of states) {
      if (state && !state.gone) baseline.set(id, state.key)
    }
    progress.value = { done: 0, failed: 0, total: baseline.size }
    if (baseline.size === 0) return
    retagging.value = true
    scheduleNext(myRun)
  }

  onBeforeUnmount(() => {
    disposed = true
    stop()
  })
  return { retagging, progress, startAfterRetag, stop }
}
