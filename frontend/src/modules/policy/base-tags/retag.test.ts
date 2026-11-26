import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ requestRetag: vi.fn() }))
const sched = vi.hoisted(() => ({ triggerJob: vi.fn() }))
const msg = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), info: vi.fn() }))
vi.mock('@/api/aiTagging', () => api)
vi.mock('@/api/scheduler', () => sched)
vi.mock('element-plus', () => ({ ElMessage: msg }))

import { ApiRequestError } from '@/api/errors'
import { MAX_POLL_TICKS, submitRetag, useListRetagPoll } from './retag'
import { TABLE_COLUMNS, mergeAiColumns, packBaseTagPatch } from './fields'
import { TABLE_COLUMNS as INTERPRET_COLUMNS, mergeInterpretAiColumns, packInterpretationPatch } from '../interpretations/fields'

afterEach(() => {
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe('retag', () => {
  it('says which task the policies went back to, and passes on what was skipped', async () => {
    const skipped = [{ reason: '手工录入或导入的政策没有源政策，不能重新打标', count: 1 }]
    api.requestRetag.mockResolvedValueOnce({ step: 'type', task: '政策类型判断', queued: 2, skipped })
    sched.triggerJob.mockRejectedValueOnce(new Error('offline'))
    expect(await submitRetag(['a', 'b', 'c'], 'type', true)).toEqual({
      message: '已把 2 条放回「政策类型判断」的待办，到任务调度执行它或等每日计划',
      skipped,
      queued: 2,
      triggered: false,
    })
    expect(api.requestRetag).toHaveBeenCalledWith(['a', 'b', 'c'], 'type')
  })

  it('auto triggers job and reports immediate background retag', async () => {
    api.requestRetag.mockResolvedValueOnce({ step: 'interpret', task: '政策解读', queued: 1, skipped: [] })
    sched.triggerJob.mockResolvedValueOnce({})
    const outcome = await submitRetag(['a'], 'interpret')
    expect(outcome.message).toContain('立即启动后台重打')
    expect(outcome.queued).toBe(1)
    expect(outcome.triggered).toBe(true)
    expect(sched.triggerJob).toHaveBeenCalledWith('policy_ai_interpret')
  })

  it('does not call triggerJob when canTrigger is false', async () => {
    api.requestRetag.mockResolvedValueOnce({ step: 'interpret', task: '政策解读', queued: 3, skipped: [] })
    const outcome = await submitRetag(['a', 'b', 'c'], 'interpret', false)
    expect(outcome).toEqual({
      message: '已把 3 条放回「政策解读」的待办，到任务调度执行它或等每日计划',
      skipped: [],
      queued: 3,
      triggered: false,
    })
    expect(sched.triggerJob).not.toHaveBeenCalled()
  })

  it('says nothing was queued when every policy was skipped', async () => {
    api.requestRetag.mockResolvedValueOnce({ step: 'interpret', task: '政策解读', queued: 0, skipped: [] })
    expect(await submitRetag(['a'], 'interpret', true)).toEqual({
      message: '没有可以重新打标的政策',
      skipped: [],
      queued: 0,
      triggered: false,
    })
    expect(sched.triggerJob).not.toHaveBeenCalled()
  })

  it('tracks the chosen rows by ID, wherever they are, and reports once every row is done', async () => {
    vi.useFakeTimers()
    const rows: Record<string, { id: string; version: number; ai_status: string }> = {
      '1': { id: '1', version: 1, ai_status: '等待重新判断类型' },
      '2': { id: '2', version: 1, ai_status: '等待重新判断类型' },
    }
    const fetchRow = vi.fn((id: string) => Promise.resolve({ id, version: 0, ai_status: '', ...rows[id] }))
    const refresh = vi.fn(() => Promise.resolve())
    const { retagging, progress, startAfterRetag, stop } = useListRetagPoll(refresh, fetchRow)
    await startAfterRetag(['1', '2', '1'])
    expect(retagging.value).toBe(true)
    expect(progress.value).toEqual({ done: 0, failed: 0, total: 2 })

    rows['1'] = { id: '1', version: 2, ai_status: '已完成' }
    await vi.advanceTimersByTimeAsync(3000)
    // 只完成一条不算结束（原来任何一行变了就报「完成」）
    expect(retagging.value).toBe(true)
    expect(progress.value.done).toBe(1)
    expect(msg.success).not.toHaveBeenCalled()

    rows['2'] = { id: '2', version: 2, ai_status: '已完成' }
    await vi.advanceTimersByTimeAsync(3000)
    expect(retagging.value).toBe(false)
    expect(msg.success).toHaveBeenCalledWith('重新打标已完成 2 条，列表数据已自动更新')
    // 第二轮起只问还没完成的那一行
    expect(fetchRow.mock.calls.slice(-1)).toEqual([['2']])
    stop()
  })

  it('counts a replaced row (404) as done, counts failures, and retries transient errors', async () => {
    vi.useFakeTimers()
    let tick = 0
    const fetchRow = vi.fn((id: string) => {
      if (tick === 0) return Promise.resolve({ id, version: 1, ai_status: '待解读' })
      if (id === 'a') return Promise.reject(new ApiRequestError({ status: 404, code: 'NOT_FOUND', message: '', requestId: null }))
      if (tick === 1) return Promise.reject(new ApiRequestError({ status: 0, code: 'NETWORK_ERROR', message: '', requestId: null }))
      return Promise.resolve({ id, version: 2, ai_status: '解读失败' })
    })
    const { retagging, progress, startAfterRetag } = useListRetagPoll(() => Promise.resolve(), fetchRow)
    await startAfterRetag(['a', 'b'])
    tick = 1
    await vi.advanceTimersByTimeAsync(3000)
    expect(progress.value).toEqual({ done: 1, failed: 0, total: 2 })
    expect(retagging.value).toBe(true)
    tick = 2
    await vi.advanceTimersByTimeAsync(3000)
    expect(retagging.value).toBe(false)
    expect(msg.warning).toHaveBeenCalledWith('重新打标结束：2 条已处理，其中 1 条失败，请按「打标状态」查看')
  })

  it('keeps asking for about 15 minutes with stepped backoff, then says it is still running', async () => {
    vi.useFakeTimers()
    const fetchRow = vi.fn((id: string) => Promise.resolve({ id, version: 1, ai_status: '待处理' }))
    const { retagging, startAfterRetag } = useListRetagPoll(() => Promise.resolve(), fetchRow)
    await startAfterRetag(['1'])
    expect(fetchRow).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(10 * 3000)
    expect(fetchRow).toHaveBeenCalledTimes(11)
    await vi.advanceTimersByTimeAsync(10 * 5000)
    expect(fetchRow).toHaveBeenCalledTimes(21)
    await vi.advanceTimersByTimeAsync(10 * 60_000)
    expect(retagging.value).toBe(true)

    await vi.advanceTimersByTimeAsync((MAX_POLL_TICKS - 20) * 10000 - 10 * 60_000)
    expect(fetchRow).toHaveBeenCalledTimes(MAX_POLL_TICKS + 1)
    await vi.advanceTimersByTimeAsync(10000)
    expect(retagging.value).toBe(false)
    expect(msg.info).toHaveBeenCalledWith('后台仍在重新打标（已处理 0 / 1 条），稍后可手动刷新查看结果')
  })

  it('does not start polling when none of the chosen rows can be read', async () => {
    const fetchRow = vi.fn(() => Promise.reject(new ApiRequestError({ status: 404, code: 'NOT_FOUND', message: '', requestId: null })))
    const { retagging, startAfterRetag } = useListRetagPoll(() => Promise.resolve(), fetchRow)
    await startAfterRetag(['x'])
    expect(retagging.value).toBe(false)
  })
})

describe('packBaseTagPatch & packInterpretationPatch', () => {
  it('splits core fields and dynamic AI output fields', () => {
    const patch = packBaseTagPatch({ policy_name: '政策A', 是否政策: '是', 判定简因: '符合政策定义' }, 3)
    expect(patch).toEqual({
      policy_name: '政策A',
      ai_outputs: { 是否政策: '是', 判定简因: '符合政策定义' },
      version: 3,
    })
    expect(mergeAiColumns(TABLE_COLUMNS, ['是否政策', '新扩展字段']).some(c => c.prop === '新扩展字段')).toBe(true)
    expect(mergeAiColumns(TABLE_COLUMNS, ['是否政策', '是否信息化政策', '信息化标签']).length).toBe(TABLE_COLUMNS.length)

    const interpPatch = packInterpretationPatch(
      { policy_title: '解读A', industry_l1: '政务', 政策亮点: '5000万补贴' },
      { policy_uid: 'uid1', version: 2 },
    )
    expect(interpPatch).toEqual({
      policy_title: '解读A',
      industry_l1: '政务',
      policy_uid: 'uid1',
      ai_outputs: { 政策亮点: '5000万补贴' },
      version: 2,
    })
    expect(mergeInterpretAiColumns(INTERPRET_COLUMNS, ['政策亮点']).some(c => c.prop === '政策亮点')).toBe(true)
    expect(mergeInterpretAiColumns(INTERPRET_COLUMNS, ['policy_title']).length).toBe(INTERPRET_COLUMNS.length)
  })
})
