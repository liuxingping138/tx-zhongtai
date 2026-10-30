import { describe, expect, it } from 'vitest'

import { configProgress, configResultText, configRunText } from './crawlerConfig'

describe('configResultText', () => {
  it('写出新标已爬、规则表编码和没对上的数量', () => {
    const result = { status: 'success', rule_rows: 26135, rule_codes: 5999, blank_code_rows: 3000, matched: 5900, marked: 12, redated: 5, unknown_codes: 99 }
    expect(configResultText(result)).toBe('新标已爬 12 个 · 上线时间对齐规则创建日期 5 个 · 规则表网站编码 5999 个，99 个信源表里没有 · 3000 行没填网站编码')
  })

  it('全部对上、没有空编码时不写多余的说明', () => {
    const result = { status: 'success', rule_rows: 2, rule_codes: 2, blank_code_rows: 0, matched: 2, marked: 0, redated: 0, unknown_codes: 0 }
    expect(configResultText(result)).toBe('新标已爬 0 个 · 规则表网站编码 2 个')
  })

  it('按栏目展开新增了行时写出来', () => {
    const result = { status: 'success', rule_rows: 226, rule_codes: 134, blank_code_rows: 0, matched: 134, marked: 0, redated: 134, unknown_codes: 0, added: 92 }
    expect(configResultText(result)).toBe('新标已爬 0 个 · 按栏目展开新增 92 行 · 上线时间对齐规则创建日期 134 个 · 规则表网站编码 134 个')
  })

  it('没有结果时返回空串', () => {
    expect(configResultText(null)).toBe('')
    expect(configResultText({ days_synced: 1 })).toBe('')
  })
})

describe('configRunText / configProgress', () => {
  it('失败时写原因，没跑过写横线', () => {
    expect(configRunText({ result: null, error_message: '同步失败（OperationalError）' })).toBe('同步失败（OperationalError）')
    expect(configRunText({ result: null, error_message: null })).toBe('—')
    expect(configProgress(null)).toBe('—')
  })
})
