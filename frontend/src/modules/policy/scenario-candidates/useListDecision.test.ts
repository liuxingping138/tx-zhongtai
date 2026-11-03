import { beforeEach, describe, expect, it, vi } from 'vitest'

const message = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: message }))

import type { CandidateItem } from '@/api/scenarioCandidates'
import type { CandidateExtras } from './useCandidateExtras'
import { useListDecision } from './useListDecision'

const row = {
  id: 'c1', name: '智慧机场工程建设管理', status: '待审', row_count: 52, kind: '新场景', main_industry: '交通行业',
  ai_verdict: '', ai_similar: '', ai_target: '', ai_reason: '', similar_level: '高', similar_name: '智慧航空 > 智慧航站楼',
} as CandidateItem
const similar = [{ path: ['智慧航空', '智慧航站楼'], score: 0.8, level: '高', desc: '', industry: '交通行业' }]

function extras(found: Partial<CandidateExtras>) {
  const entry: CandidateExtras = { loading: false, detail: null, context: null, error: '', contextError: '', ...found }
  return { ensure: vi.fn().mockResolvedValue(entry), get: vi.fn(), drop: vi.fn() }
}

describe('列表行上点了决定', () => {
  beforeEach(() => {
    message.success.mockReset()
    message.error.mockReset()
  })

  it('取到依据再开确认框；「合并」预选这一行写着的场景，传 null 是自己选', async () => {
    const source = extras({ detail: { ...row, industries: [], children: [], reasons: [] }, context: { siblings: [], similar, industries: [] } })
    const decision = useListDecision(source, vi.fn())
    await decision.open(row, 'merge')
    expect(decision.mode.value).toBe('merge')
    expect(decision.current.value?.target).toEqual(['智慧航空', '智慧航站楼'])
    await decision.open(row, 'merge', null)
    expect(decision.current.value?.target).toBeNull()
    await decision.open(row, 'adopt', ['x'])
    expect(decision.current.value?.target).toBeNull()
    expect(decision.busy.value).toBeNull()
  })

  it('详情没取到就不开确认框，说清楚', async () => {
    const decision = useListDecision(extras({ error: '网络断了' }), vi.fn())
    await decision.open(row, 'adopt')
    expect(decision.mode.value).toBeNull()
    expect(message.error).toHaveBeenCalledWith('网络断了')
  })

  it('做完提示一句、丢掉缓存、重新载入', async () => {
    const source = extras({})
    const after = vi.fn().mockResolvedValue(undefined)
    const decision = useListDecision(source, after)
    await decision.done({ ...row, status: '已采纳' })
    expect(message.success).toHaveBeenCalledWith('「智慧机场工程建设管理」已采纳进行业场景码表，提出它的 52 行解读一起改好了')
    expect(source.drop).toHaveBeenCalledWith('c1')
    expect(after).toHaveBeenCalledOnce()
  })
})
