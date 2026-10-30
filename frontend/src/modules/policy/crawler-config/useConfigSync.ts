import { computed, onScopeDispose, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getConfigSyncStatus, triggerConfigSync, type ConfigSyncStatus } from '@/api/crawlerConfig'
import { errorMessage } from '@/api/errors'
import { configResultText } from '@/modules/system/scheduler/crawlerConfig'
import { syncFailure, syncRunning } from './report'

const POLL_MS = 3000

/**
 * 爬虫配置统计页的「立即同步」：放进调度队列，排队或执行时每 3 秒看一次状态，结束后刷新统计（onFinished）。
 * 离开页面（作用域销毁）就停：清掉定时器，还在路上的请求回来后也不再排下一次，否则每进出一次页面多一条轮询。
 */
export function useConfigSync(onFinished: () => Promise<void>) {
  const status = ref<ConfigSyncStatus | null>(null)
  const syncing = ref(false)
  const running = computed(() => syncRunning(status.value))
  const failure = computed(() => syncFailure(status.value))
  let timer: ReturnType<typeof setTimeout> | undefined
  let stopped = false

  function schedule(): void {
    clearTimeout(timer)
    if (!stopped) timer = setTimeout(() => void poll(), POLL_MS)
  }

  /** 取一次状态。状态取不到不影响看统计，留着上次的，下一轮再试。 */
  async function refreshStatus(): Promise<void> {
    try {
      const latest = await getConfigSyncStatus()
      if (!stopped) status.value = latest
    } catch {
      // 下一轮再试。
    }
  }

  /** 刚跑完：刷新统计并说结果。 */
  async function finish(): Promise<void> {
    await onFinished()
    const result = status.value?.last_run
    if (!stopped && result?.status === 'success') ElMessage.success(`同步完成，${configResultText(result.result)}`)
  }

  /** 看一次状态；还在跑就 3 秒后再看，刚跑完就刷新统计。请求回来时已经离开页面的，什么都不做。 */
  async function poll(): Promise<void> {
    clearTimeout(timer)
    if (stopped) return
    const wasRunning = running.value
    await refreshStatus()
    if (stopped) return
    if (running.value) schedule()
    else if (wasRunning) await finish()
  }

  async function syncNow(): Promise<void> {
    syncing.value = true
    try {
      await triggerConfigSync()
      if (stopped) return
      ElMessage.info('已开始同步规则表，完成后自动刷新')
      status.value = { active_run: { status: 'queued' } as ConfigSyncStatus['active_run'], last_run: status.value?.last_run ?? null }
      schedule()
    } catch (cause) {
      if (!stopped) ElMessage.error(errorMessage(cause, '同步没有发起，请重试'))
    } finally {
      syncing.value = false
    }
  }

  function stop(): void {
    stopped = true
    clearTimeout(timer)
  }
  onScopeDispose(stop)

  return { status, syncing, running, failure, poll, syncNow, stop }
}
