import { describe, expect, it } from 'vitest'

import { repeatSpans } from './rowSpans'

describe('挨着的相同标题合成一格', () => {
  it('一段相同的第一行跨整段，其余不画', () => {
    expect(repeatSpans(['甲', '甲', '甲', '乙', '丙', '丙'])).toEqual([3, 0, 0, 1, 2, 0])
  })
  it('不挨着的不合并', () => {
    expect(repeatSpans(['甲', '乙', '甲'])).toEqual([1, 1, 1])
    expect(repeatSpans([])).toEqual([])
  })
})
