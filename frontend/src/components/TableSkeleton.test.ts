import { describe, expect, it } from 'vitest'
import { getSkeletonBarWidth, SKELETON_COLUMN_WIDTHS } from './tableSkeleton'

describe('tableSkeleton', () => {
  it('returns staggered widths based on row and column index', () => {
    expect(getSkeletonBarWidth(0, 0)).toBe(SKELETON_COLUMN_WIDTHS[0])
    expect(getSkeletonBarWidth(0, 1)).toBe(SKELETON_COLUMN_WIDTHS[1])
    expect(getSkeletonBarWidth(1, 0)).toBe(SKELETON_COLUMN_WIDTHS[1])
    expect(getSkeletonBarWidth(2, 6)).toBe(SKELETON_COLUMN_WIDTHS[0])
  })
})
