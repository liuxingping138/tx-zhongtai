import { ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ requestRetag: vi.fn() }))
const sched = vi.hoisted(() => ({ triggerJob: vi.fn() }))
const msg = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), info: vi.fn() }))
vi.mock('@/api/aiTagging', () => api)
vi.mock('@/api/scheduler', () => sched)
vi.mock('element-plus', () => ({ ElMessage: msg }))

import { submitRetag, useListRetagPoll } from './retag'
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
    expect(await submitRetag(['a', 'b', 'c'], 'type')).toEqual({
      message: '已把 2 条放回「政策类型判断」的待办，到任务调度执行它或等每日计划',
      skipped,
    })
    expect(api.requestRetag).toHaveBeenCalledWith(['a', 'b', 'c'], 'type')
  })

  it('auto triggers job and reports immediate background retag', async () => {
    api.requestRetag.mockResolvedValueOnce({ step: 'interpret', task: '政策解读', queued: 1, skipped: [] })
    sched.triggerJob.mockResolvedValueOnce({})
    expect((await submitRetag(['a'], 'interpret')).message).toContain('立即启动后台重打')
    expect(sched.triggerJob).toHaveBeenCalledWith('policy_ai_interpret')
  })

  it('says nothing was queued when every policy was skipped', async () => {
    api.requestRetag.mockResolvedValueOnce({ step: 'interpret', task: '政策解读', queued: 0, skipped: [] })
    expect((await submitRetag(['a'], 'interpret')).message).toBe('没有可以重新打标的政策')
  })

  it('useListRetagPoll polls until items change or max ticks reached', async () => {
    vi.useFakeTimers()
    const items = ref([{ id: '1', version: 1, ai_status: '等待重新判断类型' }])
    let calls = 0
    const refresh = vi.fn(() => {
      calls += 1
      if (calls >= 2) items.value = [{ id: '1', version: 2, ai_status: '已完成' }]
      return Promise.resolve()
    })
    const { retagging, startAfterRetag, stop } = useListRetagPoll(items, refresh)
    await startAfterRetag()
    expect(retagging.value).toBe(true)
    await vi.advanceTimersByTimeAsync(3100)
    expect(retagging.value).toBe(false)
    expect(msg.success).toHaveBeenCalledOnce()
    stop()
  })

  it('scopes polling to targetIds, ignores unrelated or missing pages, and warns on failure', async () => {
    vi.useFakeTimers()
    const items = ref([
      { id: '1', version: 1, ai_status: '待处理' },
      { id: '2', version: 1, ai_status: '待处理' },
    ])
    let step = 0
    const refresh = vi.fn(() => {
      step += 1
      if (step === 2) items.value = [{ id: '1', version: 1, ai_status: '待处理' }, { id: '2', version: 2, ai_status: '已完成' }]
      if (step === 3) items.value = [{ id: '99', version: 1, ai_status: '已完成' }]
      if (step === 4) items.value = [{ id: '1', version: 2, ai_status: '打标失败' }]
      return Promise.resolve()
    })
    const { retagging, startAfterRetag } = useListRetagPoll(items, refresh)
    await startAfterRetag(['1'])
    await vi.advanceTimersByTimeAsync(3000)
    expect(retagging.value).toBe(true)
    await vi.advanceTimersByTimeAsync(3000)
    expect(retagging.value).toBe(true)
    await vi.advanceTimersByTimeAsync(3000)
    expect(retagging.value).toBe(false)
    expect(msg.warning).toHaveBeenCalledWith('重新打标结束，部分条目失败，请查看状态')
    expect(msg.success).not.toHaveBeenCalled()
  })

  it('uses stepped backoff delays and notifies info when max ticks exhaust', async () => {
    vi.useFakeTimers()
    const items = ref([{ id: '1', version: 1, ai_status: '待处理' }])
    const refresh = vi.fn(() => Promise.resolve())
    const { retagging, startAfterRetag } = useListRetagPoll(items, refresh)
    await startAfterRetag(['1'])
    expect(refresh).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(10 * 3000)
    expect(refresh).toHaveBeenCalledTimes(11)
    expect(retagging.value).toBe(true)

    await vi.advanceTimersByTimeAsync(3000)
    expect(refresh).toHaveBeenCalledTimes(11)
    await vi.advanceTimersByTimeAsync(2000)
    expect(refresh).toHaveBeenCalledTimes(12)

    await vi.advanceTimersByTimeAsync(9 * 5000)
    expect(refresh).toHaveBeenCalledTimes(21)

    await vi.advanceTimersByTimeAsync(5000)
    expect(refresh).toHaveBeenCalledTimes(21)
    await vi.advanceTimersByTimeAsync(5000)
    expect(refresh).toHaveBeenCalledTimes(22)

    await vi.advanceTimersByTimeAsync(9 * 10000)
    expect(refresh).toHaveBeenCalledTimes(31)
    expect(retagging.value).toBe(false)
    expect(msg.info).toHaveBeenCalledWith('后台仍在重新打标，稍后可手动刷新查看结果')
  })
})

describe('packBaseTagPatch & packInterpretationPatch', () => {
  it('splits core fields and dynamic AI output fields', () => {
    const patch = packBaseTagPatch({ policy_name: '政策A', 是否政策: '是', 是否信息化政策: '是' }, 3)
    expect(patch).toEqual({
      policy_name: '政策A',
      ai_outputs: { 是否政策: '是', 是否信息化政策: '是' },
      version: 3,
    })
    expect(mergeAiColumns(TABLE_COLUMNS, ['是否政策', '新扩展字段']).some(c => c.prop === '新扩展字段')).toBe(true)
    expect(mergeAiColumns(TABLE_COLUMNS, ['是否政策']).length).toBe(TABLE_COLUMNS.length)

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
