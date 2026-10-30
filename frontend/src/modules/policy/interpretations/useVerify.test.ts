import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const message = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }))
const api = vi.hoisted(() => ({ setInterpretationsDataStatus: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: message }))
vi.mock('@/api/policy', () => api)

import { ApiRequestError } from '@/api/errors'
import type { InterpretationItem } from '@/api/policy'
import { useVerify } from './useVerify'

const row = (id: string, isNew = '否') => ({ id, is_new_scenario: isNew, data_status: '待验证' }) as InterpretationItem
const failure = (text: string) => new ApiRequestError({ status: 503, code: 'UNAVAILABLE', message: text, requestId: null })

function setup(current = row('a'), advance = vi.fn(() => Promise.resolve(true))) {
  const review = { ready: ref(true), record: ref<InterpretationItem | null>(current), advance }
  return { review, advance, ...useVerify(review) }
}

afterEach(() => vi.clearAllMocks())

describe('marking a record as verified', () => {
  it('marks it and opens the next one', async () => {
    api.setInterpretationsDataStatus.mockResolvedValueOnce({ updated: 1, unchanged: 0 })
    const { verify, advance, verifying } = setup()
    await verify(row('a'))
    expect(api.setInterpretationsDataStatus).toHaveBeenCalledWith(['a'], '人工验证')
    expect(advance).toHaveBeenCalledOnce()
    expect(message.success).toHaveBeenCalledWith('已标为人工验证，打开了下一条')
    expect(verifying.value).toBe(false)
  })

  it('says it did not change when the status update fails, and does not move on', async () => {
    api.setInterpretationsDataStatus.mockRejectedValueOnce(failure('服务暂时不可用'))
    const { verify, advance } = setup()
    await verify(row('a'))
    expect(message.error).toHaveBeenCalledWith('服务暂时不可用')
    expect(advance).not.toHaveBeenCalled()
  })

  it('says the record is verified even when the next one fails to open', async () => {
    api.setInterpretationsDataStatus.mockResolvedValueOnce({ updated: 1, unchanged: 0 })
    const { verify } = setup(row('a', '是'), vi.fn(() => Promise.reject(failure('列表暂时取不到'))))
    await verify(row('a', '是'))
    expect(message.error).not.toHaveBeenCalled()
    expect(message.warning).toHaveBeenCalledWith(
      '已标为人工验证。新增场景回列表点「同步新增场景」写进码表。没能打开下一条：列表暂时取不到',
    )
  })

  it('does nothing while the shown record is not the one in the address bar yet', async () => {
    const { verify, review } = setup()
    review.ready.value = false
    await verify(row('a'))
    review.ready.value = true
    await verify(row('b'))
    expect(api.setInterpretationsDataStatus).not.toHaveBeenCalled()
  })
})
