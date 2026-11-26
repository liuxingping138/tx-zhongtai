import { effectScope, nextTick, ref, type EffectScope } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiRequestError } from '@/api/errors'
import { useReviewRetagPoll, type ReviewRetagPollOptions } from './useReviewRetagPoll'

interface Row {
  id: string
  version: number
  ai_status: string
}

const scopes: EffectScope[] = []

function createPoll(overrides: Partial<ReviewRetagPollOptions<Row>> = {}) {
  const record = ref<Row | null>({ id: 'r1', version: 1, ai_status: '等待重新判断类型' })
  const editing = ref(false)
  const fetchRecord = vi.fn<(id: string) => Promise<Row>>()
  const reload = vi.fn<() => Promise<void>>(() => Promise.resolve())
  const onUpdated = vi.fn<(fresh: Row, baseline: Row) => void>()

  const scope = effectScope()
  scopes.push(scope)
  const poll = scope.run(() => useReviewRetagPoll<Row>({
    record: () => record.value,
    editing: () => editing.value,
    fetchRecord,
    reload,
    hasChanged: (fresh, base) => fresh.version !== base.version || fresh.ai_status !== base.ai_status,
    onUpdated,
    ...overrides,
  }))!

  return { scope, record, editing, fetchRecord, reload, onUpdated, poll }
}

afterEach(() => {
  while (scopes.length) scopes.pop()?.stop()
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe('useReviewRetagPoll', () => {
  it('polls until record changes, then reloads and notifies once', async () => {
    vi.useFakeTimers()
    const { fetchRecord, reload, onUpdated, poll } = createPoll()
    fetchRecord
      .mockResolvedValueOnce({ id: 'r1', version: 1, ai_status: '等待重新判断类型' })
      .mockResolvedValueOnce({ id: 'r1', version: 2, ai_status: '已完成' })

    await poll.start()
    expect(poll.retagging.value).toBe(true)

    await vi.advanceTimersByTimeAsync(3000)
    expect(poll.retagging.value).toBe(true)
    expect(onUpdated).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(3000)
    expect(poll.retagging.value).toBe(false)
    expect(reload).toHaveBeenCalledOnce()
    expect(onUpdated).toHaveBeenCalledWith(
      { id: 'r1', version: 2, ai_status: '已完成' },
      { id: 'r1', version: 1, ai_status: '等待重新判断类型' },
    )

    await vi.advanceTimersByTimeAsync(9000)
    expect(fetchRecord).toHaveBeenCalledTimes(2)
  })

  it('reloads baseline before starting and does not leak setInterval when unmounted mid-reload', async () => {
    vi.useFakeTimers()
    let finishReload!: () => void
    const reload = vi.fn(() => new Promise<void>((resolve) => { finishReload = resolve }))
    const { scope, fetchRecord, poll } = createPoll({ reload, reloadBeforeStart: true })

    const starting = poll.start()
    scope.stop()
    finishReload()
    await starting

    expect(poll.retagging.value).toBe(false)
    await vi.advanceTimersByTimeAsync(15_000)
    expect(fetchRecord).not.toHaveBeenCalled()
  })

  it('aborts start if record changes during reloadBeforeStart or is missing/disposed', async () => {
    vi.useFakeTimers()
    let finishReload!: () => void
    const reload = vi.fn(() => new Promise<void>((resolve) => { finishReload = resolve }))
    const { scope, record, fetchRecord, poll } = createPoll({ reload, reloadBeforeStart: true })

    const starting = poll.start()
    record.value = { id: 'r2', version: 1, ai_status: '已完成' }
    finishReload()
    await starting
    expect(poll.retagging.value).toBe(false)

    record.value = null
    await poll.start()
    expect(poll.retagging.value).toBe(false)

    scope.stop()
    record.value = { id: 'r3', version: 1, ai_status: '待解读' }
    await poll.start()
    expect(poll.retagging.value).toBe(false)
    await vi.advanceTimersByTimeAsync(9000)
    expect(fetchRecord).not.toHaveBeenCalled()
  })

  it('stops polling immediately when switching to another record', async () => {
    vi.useFakeTimers()
    const { record, fetchRecord, poll } = createPoll()
    fetchRecord.mockResolvedValue({ id: 'r1', version: 1, ai_status: '等待重新判断类型' })

    await poll.start()
    expect(poll.retagging.value).toBe(true)

    record.value = { id: 'r2', version: 1, ai_status: '已完成' }
    await nextTick()
    expect(poll.retagging.value).toBe(false)

    await vi.advanceTimersByTimeAsync(9000)
    expect(fetchRecord).not.toHaveBeenCalled()
  })

  it('stops polling after maxTicks timeout without firing onUpdated', async () => {
    vi.useFakeTimers()
    const { fetchRecord, onUpdated, poll } = createPoll({ maxTicks: 3, intervalMs: 1000 })
    fetchRecord.mockResolvedValue({ id: 'r1', version: 1, ai_status: '等待重新判断类型' })

    await poll.start()
    await vi.advanceTimersByTimeAsync(2000)
    expect(poll.retagging.value).toBe(true)
    expect(fetchRecord).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(1000)
    expect(poll.retagging.value).toBe(false)
    expect(onUpdated).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchRecord).toHaveBeenCalledTimes(2)
  })

  it('skips ticks while editing or request is in flight', async () => {
    vi.useFakeTimers()
    let release!: (row: Row) => void
    const { editing, fetchRecord, poll } = createPoll({ intervalMs: 1000 })
    fetchRecord.mockImplementationOnce(() => new Promise<Row>((resolve) => { release = resolve }))
    fetchRecord.mockResolvedValue({ id: 'r1', version: 1, ai_status: '等待重新判断类型' })

    await poll.start()
    editing.value = true
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchRecord).not.toHaveBeenCalled()

    editing.value = false
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchRecord).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchRecord).toHaveBeenCalledTimes(1)

    release({ id: 'r1', version: 1, ai_status: '等待重新判断类型' })
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(1000)
    expect(fetchRecord).toHaveBeenCalledTimes(2)
  })

  it('handles 404 via onNotFound and ignores transient errors', async () => {
    vi.useFakeTimers()
    const onNotFound = vi.fn()
    const { fetchRecord, poll } = createPoll({ onNotFound, intervalMs: 1000 })
    fetchRecord
      .mockRejectedValueOnce(new ApiRequestError({ status: 503, code: 'UNAVAILABLE', message: 'busy', requestId: null }))
      .mockRejectedValueOnce(new ApiRequestError({ status: 404, code: 'NOT_FOUND', message: 'gone', requestId: null }))

    await poll.start()
    await vi.advanceTimersByTimeAsync(1000)
    expect(poll.retagging.value).toBe(true)
    expect(onNotFound).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1000)
    expect(poll.retagging.value).toBe(false)
    expect(onNotFound).toHaveBeenCalledWith({ id: 'r1', version: 1, ai_status: '等待重新判断类型' })
  })

  it('ignores 404 when onNotFound is not provided and suppresses callbacks if switched mid-request', async () => {
    vi.useFakeTimers()
    const notFound = new ApiRequestError({ status: 404, code: 'NOT_FOUND', message: 'gone', requestId: null })
    const { fetchRecord, poll } = createPoll({ intervalMs: 1000 })
    fetchRecord.mockRejectedValueOnce(notFound)
    await poll.start()
    await vi.advanceTimersByTimeAsync(1000)
    expect(poll.retagging.value).toBe(true)
    poll.stop()

    let releaseFetch!: (row: Row) => void
    let releaseReload!: () => void
    const reload = vi.fn(() => new Promise<void>((resolve) => { releaseReload = resolve }))
    const ctx2 = createPoll({ intervalMs: 1000, reload })
    ctx2.fetchRecord.mockImplementationOnce(() => new Promise<Row>((resolve) => { releaseFetch = resolve }))
    await ctx2.poll.start()
    await vi.advanceTimersByTimeAsync(1000)
    releaseFetch({ id: 'r1', version: 2, ai_status: '已完成' })
    await Promise.resolve()
    await Promise.resolve()
    // Record switches during reload after update -> onUpdated must not fire
    ctx2.record.value = { id: 'r2', version: 1, ai_status: '已完成' }
    releaseReload()
    await Promise.resolve()
    await Promise.resolve()
    expect(ctx2.onUpdated).not.toHaveBeenCalled()

    // Error resolves after stop -> handleTickError ignores it
    let rejectFetch!: (err: unknown) => void
    const onNotFound = vi.fn()
    const ctx3 = createPoll({ intervalMs: 1000, onNotFound })
    ctx3.fetchRecord.mockImplementationOnce(() => new Promise<Row>((_, reject) => { rejectFetch = reject }))
    await ctx3.poll.start()
    await vi.advanceTimersByTimeAsync(1000)
    ctx3.poll.stop()
    rejectFetch(notFound)
    await Promise.resolve()
    expect(onNotFound).not.toHaveBeenCalled()
  })

  it('stops cleanly if record changes without watch trigger before fetch resolves', async () => {
    vi.useFakeTimers()
    let current: Row | null = { id: 'r1', version: 1, ai_status: '待解读' }
    let releaseFetch!: (row: Row) => void
    const fetchRecord = vi.fn(() => new Promise<Row>((resolve) => { releaseFetch = resolve }))
    const reload = vi.fn(() => Promise.resolve())
    const onUpdated = vi.fn()
    const scope = effectScope()
    scopes.push(scope)
    const poll = scope.run(() => useReviewRetagPoll<Row>({
      record: () => current,
      editing: () => false,
      fetchRecord,
      reload,
      hasChanged: (fresh, base) => fresh.version !== base.version,
      onUpdated,
      intervalMs: 1000,
    }))!
    await poll.start()
    await vi.advanceTimersByTimeAsync(1000)
    // Non-reactive switch so watch doesn't fire; isActive catches it when fetch resolves
    current = { id: 'r2', version: 1, ai_status: '待解读' }
    releaseFetch({ id: 'r1', version: 2, ai_status: '已完成' })
    await Promise.resolve()
    await Promise.resolve()
    expect(poll.retagging.value).toBe(false)
    expect(reload).not.toHaveBeenCalled()
    expect(onUpdated).not.toHaveBeenCalled()
  })
})
