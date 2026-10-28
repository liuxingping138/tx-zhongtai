import { describe, expect, it } from 'vitest'

import {
  CODE_TABLE_FIELD,
  appendBlock,
  costOf,
  formatState,
  formatYuan,
  insertMention,
  isActive,
  mentionAt,
  mentionOptions,
  outputFormatBlock,
  priceText,
  promptFields,
  refreshFormatBlock,
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

describe('提示词里的格式要求和输出字段对不对得上', () => {
  const block = outputFormatBlock(['行业', '场景'])

  it('读出「返回字段」那一行；没写标准格式要求时不比', () => {
    expect(promptFields(`判断行业\n\n${block}`)).toEqual(['行业', '场景'])
    expect(promptFields('3. 返回字段: 行业，场景')).toEqual(['行业', '场景'])
    expect(promptFields('只说了返回 JSON')).toBeNull()
    expect(formatState('只说了返回 JSON', ['行业'])).toBe('none')
    expect(formatState(block, [])).toBe('none')
  })

  it('字段一样就算对上，顺序不论；加了、删了字段算过时', () => {
    expect(formatState(block, ['场景', '行业'])).toBe('match')
    expect(formatState(block, ['行业', '场景', '理由'])).toBe('stale')
    expect(formatState(block, ['行业'])).toBe('stale')
  })

  it('更新只换返回字段和例如两行，前后的提示词和其余措辞不动；没有格式要求就追加整段', () => {
    const content = `判断行业\n\n${block}\n补充：理由不超过 50 字`
    const next = refreshFormatBlock(content, ['行业', '场景', '理由'])
    expect(next).toBe(content
      .replace('2、返回字段：行业、场景', '2、返回字段：行业、场景、理由')
      .replace('例如：[{"行业":"xx","场景":"xx"}]', '例如：[{"行业":"xx","场景":"xx","理由":"xx"}]'))
    expect(formatState(next, ['行业', '场景', '理由'])).toBe('match')
    expect(refreshFormatBlock('判断行业', ['行业'])).toBe(appendBlock('判断行业', outputFormatBlock(['行业'])))
  })
})

describe('模型下拉的参考价', () => {
  it('每千 token 的价换成每百万 token，去掉多余小数；写明是哪一档，联网另写按次的搜索费', () => {
    const flash = { input_price: '0.0015', output_price: '0.0045', search_price: '0.000000', web_search: false, price_note: '低优档' }
    expect(priceText(flash)).toBe('输入 ¥1.5 · 输出 ¥4.5 /百万 token · 低优档')
    expect(priceText({ ...flash, input_price: '0.000800', output_price: '0.003200', price_note: '' })).toBe('输入 ¥0.8 · 输出 ¥3.2 /百万 token')
    expect(priceText({ ...flash, web_search: true, search_price: '0.004000' }))
      .toBe('输入 ¥1.5 · 输出 ¥4.5 /百万 token · 低优档 · 联网搜索 ¥0.004/次')
  })
})
