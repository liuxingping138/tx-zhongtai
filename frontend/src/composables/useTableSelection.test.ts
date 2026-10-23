import { describe, expect, it, vi } from 'vitest'

import { useTableSelection } from './useTableSelection'

describe('列表勾选', () => {
  it('批量操作完清空勾选，表格上的勾也一起清掉', () => {
    const selection = useTableSelection<{ id: string }>()
    const clearSelection = vi.fn()
    selection.bindTable({ clearSelection })
    selection.checked.value = [{ id: 'a' }, { id: 'b' }]
    expect(selection.ids.value).toEqual(['a', 'b'])
    selection.clear()
    expect(clearSelection).toHaveBeenCalledOnce()
    expect(selection.checked.value).toEqual([])
  })

  it('表格卸载后 clear 不报错', () => {
    const selection = useTableSelection<{ id: string }>()
    selection.bindTable(null)
    selection.checked.value = [{ id: 'a' }]
    expect(() => selection.clear()).not.toThrow()
    expect(selection.ids.value).toEqual([])
  })
})
