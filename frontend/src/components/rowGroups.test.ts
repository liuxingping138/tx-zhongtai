import { describe, expect, it } from 'vitest'

import { groupConsecutive, isGroupRow, type GroupRow } from './rowGroups'

const rows = (...titles: string[]) => titles.map((title, index) => ({ id: String(index), title }))

describe('挨着的相同标题分成一组', () => {
  it('每组前面一行分组标题，下面是这组的行', () => {
    const out = groupConsecutive(rows('甲', '甲', '乙'), row => row.title)
    expect(out.map(row => (isGroupRow(row) ? `#${row.group.title}` : row.id))).toEqual(['#甲', '0', '1', '#乙', '2'])
    const first = out[0]
    expect(isGroupRow(first) && first.group.rows.map(row => row.id)).toEqual(['0', '1'])
  })

  it('只分挨着的：隔开的同名标题各成一组，分组行 id 不撞', () => {
    const out = groupConsecutive(rows('甲', '乙', '甲'), row => row.title)
    const groups = out.filter(row => isGroupRow(row)) as GroupRow<{ id: string; title: string }>[]
    expect(groups.map(group => group.group.title)).toEqual(['甲', '乙', '甲'])
    expect(new Set(groups.map(group => group.id)).size).toBe(3)
  })

  it('没有行时什么都没有', () => {
    expect(groupConsecutive([], () => '')).toEqual([])
  })
})
