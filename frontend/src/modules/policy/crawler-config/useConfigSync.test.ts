import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'

const message = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }))
const api = vi.hoisted(() => ({ getConfigSyncStatus: vi.fn(), triggerConfigSync: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: message }))
vi.mock('@/api/crawlerConfig', () => api)

import type { ConfigSyncStatus } from '@/api/crawlerConfig'
import { useConfigSync } from './useConfigSync'

const RUNNING = { active_run: { status: 'running' }, last_run: null } as unknown as ConfigSyncStatus
const DONE = {
  active_run: null,
  last_run: { status: 'success', result: { status: 'success', rule_rows: 3, marked: 1 } },
} as unknown as ConfigSyncStatus

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function setup() {
  const onFinished = vi.fn(() => Promise.resolve())
  const scope = effectScope()
  const sync = scope.run(() => useConfigSync(onFinished))!
  return { sync, scope, onFinished }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('config sync polling', () => {
  it('checks every 3 seconds while syncing and refreshes the report once it is done', async () => {
    api.getConfigSyncStatus.mockResolvedValueOnce(RUNNING).mockResolvedValueOnce(RUNNING).mockResolvedValueOnce(DONE)
    const { sync, onFinished, scope } = setup()
    await sync.poll()
    expect(sync.running.value).toBe(true)
    await vi.advanceTimersByTimeAsync(3000)
    await vi.advanceTimersByTimeAsync(3000)
    expect(api.getConfigSyncStatus).toHaveBeenCalledTimes(3)
    expect(onFinished).toHaveBeenCalledOnce()
    expect(message.success).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(api.getConfigSyncStatus).toHaveBeenCalledTimes(3)
    scope.stop()
  })

  it('stops when the page is left, even with a status request still on its way', async () => {
    const pending = deferred<ConfigSyncStatus>()
    api.getConfigSyncStatus.mockResolvedValueOnce(RUNNING).mockReturnValueOnce(pending.promise)
    const { sync, scope, onFinished } = setup()
    await sync.poll()
    await vi.advanceTimersByTimeAsync(3000)
    expect(api.getConfigSyncStatus).toHaveBeenCalledTimes(2)
    // 第二次请求还没回来时离开页面；它回来后不能再排下一次。
    scope.stop()
    pending.resolve(RUNNING)
    await vi.advanceTimersByTimeAsync(30_000)
    expect(api.getConfigSyncStatus).toHaveBeenCalledTimes(2)
    expect(onFinished).not.toHaveBeenCalled()
  })

  it('cancels the next check when the page is left between checks', async () => {
    api.getConfigSyncStatus.mockResolvedValue(RUNNING)
    const { sync, scope } = setup()
    await sync.poll()
    scope.stop()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(api.getConfigSyncStatus).toHaveBeenCalledOnce()
  })

  it('does not start polling when the page was left before the sync request came back', async () => {
    const pending = deferred<unknown>()
    api.triggerConfigSync.mockReturnValueOnce(pending.promise)
    const { sync, scope } = setup()
    const started = sync.syncNow()
    scope.stop()
    pending.resolve({ status: 'queued' })
    await started
    await vi.advanceTimersByTimeAsync(30_000)
    expect(api.getConfigSyncStatus).not.toHaveBeenCalled()
    expect(message.info).not.toHaveBeenCalled()
  })

  it('polls once after starting a sync, without stacking a second loop', async () => {
    api.triggerConfigSync.mockResolvedValueOnce({ status: 'queued' })
    api.getConfigSyncStatus.mockResolvedValue(RUNNING)
    const { sync, scope } = setup()
    await sync.poll()
    await sync.syncNow()
    expect(sync.running.value).toBe(true)
    await vi.advanceTimersByTimeAsync(3000)
    // 页面打开时那一轮和「立即同步」后的那一轮合成一条，3 秒只问一次。
    expect(api.getConfigSyncStatus).toHaveBeenCalledTimes(2)
    scope.stop()
  })
})
