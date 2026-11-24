import { describe, expect, it } from 'vitest'

import {
  buildPageText,
  findInPage,
  matchLabel,
  normalizeQuery,
  segmentsByItem,
  splitBySegments,
  textSource,
  toItemRanges,
} from './pdfSearch'

describe('pdfSearch', () => {
  it('查找词去首尾空白、不分大小写，空白统一成普通空格', () => {
    expect(normalizeQuery('  AI　Agent ')).toBe('ai agent')
    expect(normalizeQuery('   ')).toBe('')
  })

  it('文字块首尾相接拼成整页文本，跨块也能命中', () => {
    const page = buildPageText(['数字政', '府建设', 'PDF'])
    expect(page.text).toBe('数字政府建设pdf')
    expect(page.starts).toEqual([0, 3, 6])
    expect(findInPage(page, '政府')).toEqual([{ start: 2, end: 4 }])
    expect(toItemRanges(page, { start: 2, end: 4 })).toEqual([
      { item: 0, from: 2, to: 3 },
      { item: 1, from: 0, to: 1 },
    ])
  })

  it('同一页的多处匹配互不重叠；空查找词没有匹配', () => {
    const page = buildPageText(['aaaa'])
    expect(findInPage(page, 'aa')).toEqual([{ start: 0, end: 2 }, { start: 2, end: 4 }])
    expect(findInPage(page, '')).toEqual([])
  })

  it('小写后长度会变的块按原文找，位置不错位', () => {
    const page = buildPageText(['İx', 'ab'])
    expect(page.text).toBe('İxab')
    expect(findInPage(page, 'ab')).toEqual([{ start: 2, end: 4 }])
  })

  it('跳过空块；没有文字块或空匹配时没有片段', () => {
    const page = buildPageText(['ab', '', 'cd'])
    expect(toItemRanges(page, { start: 1, end: 3 })).toEqual([
      { item: 0, from: 1, to: 2 },
      { item: 2, from: 0, to: 1 },
    ])
    expect(toItemRanges(buildPageText([]), { start: 0, end: 1 })).toEqual([])
    expect(toItemRanges(page, { start: 2, end: 2 })).toEqual([])
  })

  it('按文字块分组并标出当前那处，再把块文字切成高亮段', () => {
    const page = buildPageText(['政府政府', '政'])
    const matches = findInPage(page, '政府')
    const segments = segmentsByItem(page, matches, 1)
    expect(segments.get(0)).toEqual([
      { from: 0, to: 2, selected: false },
      { from: 2, to: 4, selected: true },
    ])
    expect(segments.has(1)).toBe(false)
    expect(splitBySegments('x政府y', [{ from: 1, to: 3, selected: true }])).toEqual([
      ['x', null],
      ['政府', { from: 1, to: 3, selected: true }],
      ['y', null],
    ])
    expect(splitBySegments('政府', [{ from: 0, to: 2, selected: false }])).toEqual([['政府', { from: 0, to: 2, selected: false }]])
  })

  it('进度文字：找到几处、是否还在往后找', () => {
    expect(matchLabel(-1, 0, true)).toBe('正在查找…')
    expect(matchLabel(-1, 0, false)).toBe('无匹配')
    expect(matchLabel(0, 3, true)).toBe('第 1 / 3+ 处')
    expect(matchLabel(2, 3, false)).toBe('第 3 / 3 处')
  })
  it('换行处两边都是西文时补一个空格，跨行也能找到；中文换行仍首尾相接', () => {
    const latin = buildPageText(['digital', 'government'], [true, false])
    expect(latin.text).toBe('digital government')
    expect(latin.starts).toEqual([0, 8])
    const [match] = findInPage(latin, normalizeQuery('digital government'))
    expect(toItemRanges(latin, match!)).toEqual([{ item: 0, from: 0, to: 7 }, { item: 1, from: 0, to: 10 }])

    expect(buildPageText(['数字政', '府建设'], [true, false]).text).toBe('数字政府建设')
    expect(buildPageText(['数字', 'Gov'], [true, false]).text).toBe('数字gov')
    expect(buildPageText(['end.', ' next'], [true, false]).text).toBe('end. next') // 本来就有空格，不再补
    expect(buildPageText(['of', 'line'], [false, false]).text).toBe('ofline') // 不是换行不补
  })

  it('换行记在空块上时，按换行前最后一个有字的块判断', () => {
    const page = buildPageText(['of', '', 'line'], [false, true, false])
    expect(page.text).toBe('of line')
    expect(page.starts).toEqual([0, 2, 3])
    const [match] = findInPage(page, 'of line')
    expect(toItemRanges(page, match!)).toEqual([{ item: 0, from: 0, to: 2 }, { item: 2, from: 0, to: 4 }])
  })

  it('getTextContent 的条目换成文字块：跳过标记内容，带上换行标记', () => {
    expect(textSource([{ str: 'a', hasEOL: true }, { type: 'beginMarkedContent' }, { str: 'b' }])).toEqual({ items: ['a', 'b'], eol: [true, false] })
  })
})
