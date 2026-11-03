import { describe, expect, it } from 'vitest'

import type { AiModel } from '@/api/ai'
import { applyStreamEvent, type StreamTarget } from './streamEvents'

function target(): StreamTarget {
  return {
    user: { text: '原文' },
    reply: { text: '', reasoning: '', tip: '', error: '' },
    stats: { model: null, usage: { input: 0, output: 0, search: 0 } },
  }
}

describe('流式事件', () => {
  it('依次处理实际提示词、模型、思考、正文、联网和用量，response_id 不用（多轮对话已删）', () => {
    const t = target()
    const model = { id: 'm', name: '模型' } as AiModel
    for (const event of [
      { prompt: '替换后的提示词' },
      { model },
      { reasoning: '想' },
      { tool_event: { stage: 'web_search_in_progress', message: '已发起联网搜索' } },
      { tool_event: { stage: 'web_search_in_progress', message: '已发起联网搜索' } },
      { text: '你' },
      { text: '好' },
      { usage: { input_tokens: 10, output_tokens: 5 } },
      { response_id: 'resp_1' },
    ]) applyStreamEvent(t, event)
    expect(t.user.text).toBe('替换后的提示词')
    expect(t.stats.model).toBe(model)
    expect(t.reply).toMatchObject({ text: '你好', reasoning: '想', tip: '已发起联网搜索' })
    expect(t.stats.usage).toEqual({ input: 10, output: 5, search: 2 })
  })

  it('usage 带权威联网次数时覆盖事件计数；错误和未知事件', () => {
    const t = target()
    applyStreamEvent(t, { tool_event: { stage: 'web_search_in_progress' } })
    applyStreamEvent(t, { usage: { web_search: 4 } })
    applyStreamEvent(t, { error: '限流' })
    applyStreamEvent(t, { unknown: 1, text: 3, model: null })
    expect(t.stats.usage.search).toBe(4)
    expect(t.reply.error).toBe('限流')
    expect(t.reply.text).toBe('')
  })

  it('试发按输出字段解析的结果：解析出的列表，或者 null（格式不对），都要记下', () => {
    const ok = target()
    applyStreamEvent(ok, { parsed: [{ 行业: '制造' }] })
    expect(ok.reply.parsed).toEqual([{ 行业: '制造' }])
    const bad = target()
    applyStreamEvent(bad, { parsed: null })
    expect(bad.reply.parsed).toBeNull()
    const none = target()
    applyStreamEvent(none, { text: '答' })
    expect(none.reply.parsed).toBeUndefined()
  })
})
