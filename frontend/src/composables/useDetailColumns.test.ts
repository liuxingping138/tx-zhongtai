import { describe, expect, it } from 'vitest'

import { useDetailColumns } from './useDetailColumns'

const groups = [
  { title: '基础', hint: '', fields: [{ key: 'name', label: '名称' }, { key: 'remark', label: '备注' }] },
  { title: '其他', hint: '', fields: [{ key: 'owner', label: '负责人' }] },
]

describe('useDetailColumns', () => {
  it('表格列在前，表单里有而表格没有的字段按表单顺序补在后面', () => {
    const { columns } = useDetailColumns([{ prop: 'name', label: '名称', width: 200 }], groups)
    expect(columns.map(col => col.prop)).toEqual(['name', 'remark', 'owner'])
    expect(columns[0]?.width).toBe(200)
  })

  it('叠进别的列里显示的下级字段不再单独成列', () => {
    const { columns } = useDetailColumns([{ prop: 'name', label: '名称', stack: ['remark'] }], groups)
    expect(columns.map(col => col.prop)).toEqual(['name', 'owner'])
  })

  it('默认显示全部列，选中项是独立的副本', () => {
    const { defaults, selected } = useDetailColumns([], groups)
    expect(selected.value).toEqual(defaults)
    selected.value.pop()
    expect(defaults).toHaveLength(3)
  })
})
