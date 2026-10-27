import { describe, expect, it } from 'vitest'

import { itemSummary, rowLayout } from './runRowLayout'

const FIELDS = ['政策概览', '一级行业', '一级场景', '机会类型']

describe('一行解析出多条时的摆法', () => {
  it('只有一条：照常全列', () => {
    expect(rowLayout([{ 政策概览: '概览' }], FIELDS)).toEqual({ shared: [], own: FIELDS })
    expect(rowLayout([], FIELDS)).toEqual({ shared: [], own: FIELDS })
  })

  it('多条：各条都一样的字段只列一次，其余在每条里列', () => {
    const items = [
      { 政策概览: '概览', 一级行业: '政务', 一级场景: '智慧城市', 机会类型: 'TO_G' },
      { 政策概览: '概览', 一级行业: '教育', 一级场景: '智慧校园', 机会类型: 'TO_G' },
    ]
    expect(rowLayout(items, FIELDS)).toEqual({ shared: ['政策概览', '机会类型'], own: ['一级行业', '一级场景'] })
  })

  it('摘要取前几个不一样的字段，空值跳过；全一样时说明一下', () => {
    expect(itemSummary({ 一级行业: '政务', 一级场景: ' ', 二级场景: '一网通办' }, ['一级行业', '一级场景', '二级场景'])).toBe('政务 · 一网通办')
    expect(itemSummary({ 一级行业: '政务' }, [])).toBe('和上面相同')
  })
})
