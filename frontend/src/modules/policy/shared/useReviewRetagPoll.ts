import { onScopeDispose, ref, watch } from 'vue'
import { isApiError } from '@/api/errors'

export interface ReviewRetagPollOptions<Row extends { id: string }> {
  /** 当前核对页正在看的记录。 */
  record: () => Row | null
  /** 是否正在编辑（编辑中跳过本轮询问，不打断用户输入）。 */
  editing: () => boolean
  /** 按 ID 查询后端最新记录。 */
  fetchRecord: (id: string) => Promise<Row>
  /** 刷新核对页数据（开始前可选刷新一次，变化后刷新展示）。 */
  reload: () => Promise<void>
  /** 开始轮询前是否先 reload 一次以拿到最新基线（基础标签重打标会立即改 ai_status/version）。 */
  reloadBeforeStart?: boolean
  /** 判断后端记录是否已相对基线发生变化。 */
  hasChanged: (fresh: Row, baseline: Row) => boolean
  /** 记录已更新并 reload 完毕后的回调（如弹成功/失败提示）。 */
  onUpdated: (fresh: Row, baseline: Row) => void | Promise<void>
  /** 记录返回 404（如重新解读替换了旧行）时的处理；不传则与普通网络抖动一样忽略并继续重试。 */
  onNotFound?: (baseline: Row) => void | Promise<void>
  intervalMs?: number
  maxTicks?: number
}

const DEFAULT_INTERVAL_MS = 3000
const DEFAULT_MAX_TICKS = 30

/**
 * 核对页单条记录重新打标后的后台轮询：
 * - 支持开始前先 reload 一次拿新基线，并在 `await reload()` 期间防卸载/翻条导致的 setInterval 泄漏；
 * - 监听当前记录 ID，翻到别的记录立即停轮询；
 * - 编辑中或上一次请求未返回时跳过本轮，网络抖动忽略，超过最大次数自动停止。
 */
export function useReviewRetagPoll<Row extends { id: string }>(options: ReviewRetagPollOptions<Row>) {
  const intervalMs = options.intervalMs ?? DEFAULT_INTERVAL_MS
  const maxTicks = options.maxTicks ?? DEFAULT_MAX_TICKS

  const retagging = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null
  let remaining = 0
  let activeId = ''
  let inFlight = false
  let disposed = false
  let runId = 0

  function stop() {
    runId += 1
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
    remaining = 0
    activeId = ''
    inFlight = false
    retagging.value = false
  }

  function isActive(myRun: number, baseId: string): boolean {
    if (disposed || myRun !== runId) return false
    if (options.record()?.id === baseId) return true
    stop()
    return false
  }

  async function applyUpdate(fresh: Row, baseline: Row) {
    stop()
    const ended = runId
    await options.reload()
    if (disposed || ended !== runId) return
    if (options.record()?.id !== baseline.id) return
    await options.onUpdated(fresh, baseline)
  }

  async function handleTickError(myRun: number, baseline: Row, cause: unknown) {
    if (!isActive(myRun, baseline.id)) return
    if (!options.onNotFound || !isApiError(cause) || cause.status !== 404) return
    stop()
    await options.onNotFound(baseline)
  }

  async function tick(myRun: number, baseline: Row) {
    if (options.editing() || inFlight || !isActive(myRun, baseline.id)) return
    inFlight = true
    try {
      const fresh = await options.fetchRecord(baseline.id)
      if (isActive(myRun, baseline.id) && options.hasChanged(fresh, baseline)) {
        await applyUpdate(fresh, baseline)
      }
    } catch (cause) {
      await handleTickError(myRun, baseline, cause)
    } finally {
      if (myRun === runId) inFlight = false
    }
  }

  async function start() {
    stop()
    if (disposed) return
    const myRun = runId
    const initialId = options.record()?.id
    if (!initialId) return
    if (options.reloadBeforeStart) {
      await options.reload()
      if (disposed || myRun !== runId) return
    }
    const baseline = options.record()
    if (!baseline || baseline.id !== initialId) return
    retagging.value = true
    activeId = baseline.id
    remaining = maxTicks
    timer = setInterval(() => {
      remaining -= 1
      if (remaining <= 0) {
        stop()
        return
      }
      void tick(myRun, baseline)
    }, intervalMs)
  }

  watch(() => options.record()?.id, (id) => {
    if (activeId && id !== activeId) stop()
  })

  onScopeDispose(() => {
    disposed = true
    stop()
  })

  return { retagging, start, stop }
}
