import { describe, expect, it } from 'vitest'
import { layoutDataColumns } from './dataColumnLayout'
import type { DataColumn } from './dataColumns'

describe('business table column layout', () => {
  const columns: DataColumn[] = [
    { prop: 'province', label: '省份', width: 100 },
    { prop: 'title', label: '标题', minWidth: 300, grow: 2 },
    { prop: 'description', label: '说明', minWidth: 200, grow: 1 },
  ]

  it('keeps short fields compact and assigns extra space to reading content', () => {
    expect(layoutDataColumns(columns, 850, 100).map(c => c.width)).toEqual([100, 400, 250])
    expect(layoutDataColumns([columns[0]!], 1400, 100)[0]!.width).toBe(100)
  })

  it('fills a wide surface without stretching short fields or leaving a rounding gap', () => {
    const result = layoutDataColumns(columns, 2560, 116)
    expect(result[0]!.width).toBe(100)
    expect(result.reduce((sum, c) => sum + c.width, 116)).toBe(2560)
    expect(layoutDataColumns([columns[1]!], 1400, 100)[0]!.width).toBe(1300)
  })

  it('preserves readable minimums when all columns exceed the viewport', () => {
    expect(layoutDataColumns(columns, 500, 100).map(c => c.width)).toEqual([100, 300, 200])
    expect(layoutDataColumns(columns, 0, 100).map(c => c.width)).toEqual([100, 300, 200])
  })

  it('preserves field order and does not mutate column definitions', () => {
    expect(layoutDataColumns(columns, 1400, 100).map(c => c.prop)).toEqual(['province', 'title', 'description'])
    expect(columns.map(c => c.width)).toEqual([100, undefined, undefined])
  })
})
