import { describe, expect, it } from 'vitest'

import {
  CODE_TABLE_FIELD,
  appendBlock,
  costOf,
  formatYuan,
  insertMention,
  isActive,
  mentionAt,
  mentionOptions,
  outputFormatBlock,
  runModeText,
  runStatusType,
  splitFields,
} from './aiText'

describe('输出字段', () => {
  it('竖线分隔，忽略空段', () => {
    expect(splitFields(' 行业 | |场景|')).toEqual(['行业', '场景'])
  })

  it('拼出与旧系统一致的返回格式要求，空内容时直接作为内容', () => {
    const block = outputFormatBlock(['行业', '场景'])
    expect(block).toContain('2、返回字段：行业、场景')
    expect(block).toContain('例如：[{"行业":"xx","场景":"xx"}]')
    expect(appendBlock('原文  \n', block)).toBe(`原文\n\n${block}`)
    expect(appendBlock('  ', block)).toBe(block)
  })
})

describe('@ 插入变量', () => {
  it('光标前紧邻的 @ 才触发，遇到空白或已闭合的变量不触发', () => {
    expect(mentionAt('企业 @名', 5)).toEqual({ at: 3, keyword: '名' })
    expect(mentionAt('企业 @名 称', 7)).toBeNull()
    expect(mentionAt('@【名称】 后', 7)).toBeNull()
    expect(mentionAt('没有', 2)).toBeNull()
  })

  it('候选含表头，上传了码表时加上码表项，按关键词过滤', () => {
    expect(mentionOptions(['名称', '地址'], true, '')).toEqual(['名称', '地址', CODE_TABLE_FIELD])
    expect(mentionOptions(['名称', '地址'], false, '地')).toEqual(['地址'])
  })

  it('替换 @ 与过滤词并把光标放到变量后', () => {
    expect(insertMention('企业 @名 结尾', 3, 5, '名称')).toEqual({ text: '企业 @【名称】 结尾', caret: 8 })
  })
})

describe('费用与状态', () => {
  it('按千 token 单价和联网单价计算', () => {
    const model = { input_price: '0.0015', output_price: '0.0045', search_price: '0.004' }
    const cost = costOf(model, { input: 2000, output: 1000, search: 3 })
    expect(cost.inference).toBeCloseTo(0.0075)
    expect(cost.search).toBeCloseTo(0.012)
    expect(costOf(undefined, { input: 1, output: 1, search: 1 })).toEqual({ inference: 0, search: 0 })
    expect(formatYuan(0.00751)).toBe('¥0.0075')
  })

  it('状态颜色与是否仍在运行', () => {
    expect(['done', 'failed', 'interrupted', 'running', 'cancelled'].map(s => runStatusType(s as never))).toEqual(['success', 'danger', 'warning', 'primary', 'info'])
    expect(isActive('stopping')).toBe(true)
    expect(isActive('cancelled')).toBe(false)
  })
})

describe('运行范围', () => {
  it('只跑前几条写条数，不限条数写全部', () => {
    expect(runModeText({ row_limit: 10 })).toBe('前 10 条')
    expect(runModeText({ row_limit: 0 })).toBe('全部')
  })
})
