import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ requestRetag: vi.fn() }))
vi.mock('@/api/aiTagging', () => api)

import { submitRetag } from './retag'

afterEach(() => vi.clearAllMocks())

describe('retag', () => {
  it('says which task the policies went back to, and passes on what was skipped', async () => {
    const skipped = [{ reason: '手工录入或导入的政策没有源政策，不能重新打标', count: 1 }]
    api.requestRetag.mockResolvedValueOnce({ step: 'type', task: '政策类型判断', queued: 2, skipped })
    expect(await submitRetag(['a', 'b', 'c'], 'type')).toEqual({
      message: '已把 2 条放回「政策类型判断」的待办，到任务调度执行它或等每日计划',
      skipped,
    })
    expect(api.requestRetag).toHaveBeenCalledWith(['a', 'b', 'c'], 'type')
  })

  it('says nothing was queued when every policy was skipped', async () => {
    api.requestRetag.mockResolvedValueOnce({ step: 'interpret', task: '政策解读', queued: 0, skipped: [] })
    expect((await submitRetag(['a'], 'interpret')).message).toBe('没有可以重新打标的政策')
  })
})

import { TABLE_COLUMNS, mergeAiColumns, packBaseTagPatch } from './fields'

describe('packBaseTagPatch', () => {
  it('splits core fields and dynamic AI output fields', () => {
    const patch = packBaseTagPatch({ policy_name: '政策A', 是否政策: '是', 是否信息化政策: '是' }, 3)
    expect(patch).toEqual({
      policy_name: '政策A',
      ai_outputs: { 是否政策: '是', 是否信息化政策: '是' },
      version: 3,
    })
    const merged = mergeAiColumns(TABLE_COLUMNS, ['是否政策', '新扩展字段'])
    expect(merged.some(c => c.prop === '新扩展字段')).toBe(true)
  })
})
