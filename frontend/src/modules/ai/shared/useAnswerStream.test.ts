import { describe, expect, it, vi } from 'vitest'

const stream = vi.hoisted(() => ({ events: [] as Record<string, unknown>[], fail: null as Error | null }))
vi.mock('@/api/eventStream', () => ({
  postEventStream: (_path: string, _body: unknown, onEvent: (event: Record<string, unknown>) => void, signal: AbortSignal) => {
    if (stream.fail) return Promise.reject(signal.aborted ? new Error('aborted') : stream.fail)
    for (const event of stream.events) onEvent(event)
    return Promise.resolve()
  },
}))

import { useAnswerStream } from './useAnswerStream'

describe('useAnswerStream', () => {
  it('一问一答进消息列表，记录用量和费用', async () => {
    stream.events = [
      { model: { id: 'm', name: '模型', input_price: '0.001', output_price: '0.002', search_price: '0' } },
      { text: '答' },
      { usage: { input_tokens: 1000, output_tokens: 1000 } },
      { response_id: 'r1' },
    ]
    stream.fail = null
    const answer = useAnswerStream()
    await answer.send('/ai/stream/ask', {}, '问', true)
    expect(answer.messages.value.map(item => [item.role, item.text])).toEqual([['user', '问'], ['assistant', '答']])
    expect(answer.stats.thinking).toBe(true)
    expect(answer.cost.value.inference).toBeCloseTo(0.003)
    expect(answer.running.value).toBe(false)
    answer.clear()
    expect(answer.messages.value).toEqual([])
  })

  it('请求失败或没有内容时把原因写在回答里', async () => {
    stream.events = []
    stream.fail = null
    const answer = useAnswerStream()
    await answer.send('/ai/stream/ask', {}, '问', false)
    expect(answer.messages.value[1]?.error).toBe('模型没有返回内容，请稍后重试')
    stream.fail = Object.assign(new Error('x'), { status: 422, code: 'VALIDATION_ERROR', message: '未知模型' })
    await answer.send('/ai/stream/ask', {}, '问', false)
    expect(answer.messages.value[3]?.error).toBe('未知模型')
  })
})
