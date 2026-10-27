import { describe, expect, it } from 'vitest'
import { foldFilterFields, type FilterFieldBox } from './filterFold'

const box = (top: number, filled = false, height = 62): FilterFieldBox => ({ top, height, filled })

describe('filter field folding', () => {
  it('folds every field below the first row and counts the filled ones', () => {
    const result = foldFilterFields([box(0), box(0, true), box(0), box(74, true), box(74), box(148, true)])
    expect(result.folded).toEqual([3, 4, 5])
    expect(result.foldedFilled).toBe(2)
    expect(result.firstRowBottom).toBe(62)
  })

  it('keeps a shorter bottom-aligned field on the first row', () => {
    // 没有标题的框矮 26px，和同一行的框底边对齐，顶边更低但仍在第一行。
    expect(foldFilterFields([box(0), box(26, false, 36), box(74)]).folded).toEqual([2])
  })

  it('tolerates sub-pixel rounding inside the first row', () => {
    expect(foldFilterFields([box(0), box(0.6), box(0.4)]).folded).toEqual([])
  })

  it('has nothing to fold when every field fits or there are none', () => {
    expect(foldFilterFields([box(0, true), box(0, true)])).toEqual({ folded: [], foldedFilled: 0, firstRowBottom: 62 })
    expect(foldFilterFields([])).toEqual({ folded: [], foldedFilled: 0, firstRowBottom: 0 })
  })
})
