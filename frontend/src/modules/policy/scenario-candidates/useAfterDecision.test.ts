import { beforeEach, describe, expect, it, vi } from 'vitest'

const message = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: message }))

import type { CandidateItem } from '@/api/scenarioCandidates'
import { useAfterDecision } from './useAfterDecision'

const merged = { status: '已合并' } as CandidateItem

describe('做完决定接着打开下一个', () => {
  beforeEach(() => {
    message.success.mockReset()
    message.warning.mockReset()
  })

  it('打开了下一个', async () => {
    await useAfterDecision({ advance: () => Promise.resolve(true) }).finished(merged)
    expect(message.success).toHaveBeenCalledWith('已合并到已有场景，打开了下一个')
  })

  it('已经是最后一个就停在原页', async () => {
    await useAfterDecision({ advance: () => Promise.resolve(false) }).finished({ status: '已驳回' } as CandidateItem)
    expect(message.success).toHaveBeenCalledWith('已驳回')
  })

  it('决定已生效、只是下一个没打开，不说成没成功', async () => {
    await useAfterDecision({ advance: () => Promise.reject(new Error('网络')) }).finished(merged)
    expect(message.warning.mock.calls[0]?.[0]).toMatch(/^已合并到已有场景。没能打开下一个/)
    expect(message.success).not.toHaveBeenCalled()
  })
})
