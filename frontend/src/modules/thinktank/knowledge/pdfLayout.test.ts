import { describe, expect, it } from 'vitest'
import {
  clampPage,
  clampScale,
  fitWidthScale,
  LOW_DPR_FLOOR,
  MAX_CANVAS_PIXELS,
  MAX_SCALE,
  MIN_SCALE,
  mostVisiblePage,
  NARROW_PAGE_WIDTH,
  outputScale,
  pagesToRender,
  stepZoom,
  VIEW_GUTTER,
  zoomLabel,
} from './pdfLayout'

describe('pdfLayout', () => {
  it('适合宽度扣掉两边留白，夹在缩放范围内；容器还没量出来时按 100%', () => {
    expect(fitWidthScale(595 + VIEW_GUTTER * 2, 595)).toBe(1)
    expect(fitWidthScale(1190 + VIEW_GUTTER * 2, 595)).toBe(2)
    expect(fitWidthScale(0, 595)).toBe(1)
    expect(fitWidthScale(800, 0)).toBe(1)
    expect(fitWidthScale(100, 595)).toBe(MIN_SCALE)
    expect(fitWidthScale(100_000, 595)).toBe(MAX_SCALE)
  })

  it('放大缩小按档走，落在两档之间时走到相邻那档，到头不再变', () => {
    expect(stepZoom(1, 1)).toBe(1.1)
    expect(stepZoom(1, -1)).toBe(0.9)
    expect(stepZoom(1.37, 1)).toBe(1.5)
    expect(stepZoom(1.37, -1)).toBe(1.25)
    expect(stepZoom(MAX_SCALE, 1)).toBe(MAX_SCALE)
    expect(stepZoom(MIN_SCALE, -1)).toBe(MIN_SCALE)
    expect(clampScale(Number.NaN)).toBe(1)
    expect(zoomLabel(1.254)).toBe('125%')
  })

  it('页码跳转夹到首尾，非数字回到当前页', () => {
    expect(clampPage(0, 55)).toBe(1)
    expect(clampPage(99, 55)).toBe(55)
    expect(clampPage(3.6, 55)).toBe(4)
    expect(clampPage(Number.NaN, 55, 7)).toBe(7)
    expect(clampPage(5, 0)).toBe(1)
  })

  it('只渲染可见页和上下缓冲页', () => {
    expect([...pagesToRender([1], 55)].sort((a, b) => a - b)).toEqual([1, 2, 3])
    expect([...pagesToRender([10, 11], 55)].sort((a, b) => a - b)).toEqual([8, 9, 10, 11, 12, 13])
    expect([...pagesToRender([55], 55, 1)].sort((a, b) => a - b)).toEqual([54, 55])
    expect(pagesToRender([], 55).size).toBe(0)
  })

  it('当前页取可见比例最大的，一样大取靠前的，没有可见页保持原值', () => {
    expect(mostVisiblePage(new Map([[3, 0.2], [4, 0.8]]), 1)).toBe(4)
    expect(mostVisiblePage(new Map([[5, 0.5], [4, 0.5]]), 1)).toBe(4)
    expect(mostVisiblePage(new Map(), 7)).toBe(7)
  })

  it('画布像素倍数跟设备像素比，但不超过上限', () => {
    expect(outputScale(600, 800, 2)).toBe(2)
    expect(outputScale(1200, 800, 0)).toBe(1)
    expect(outputScale(0, 0, 2)).toBe(2)
    const ratio = outputScale(4000, 6000, 3)
    expect(ratio).toBeLessThan(3)
    expect(4000 * 6000 * ratio * ratio).toBeLessThanOrEqual(MAX_CANVAS_PIXELS + 1)
  })

  it('oversamples narrow pages on 1x screens so split-pane previews stay crisp', () => {
    expect(outputScale(600, 800, 1)).toBe(LOW_DPR_FLOOR)
    expect(outputScale(600, 800, 1.25)).toBe(LOW_DPR_FLOOR)
    expect(outputScale(NARROW_PAGE_WIDTH, 1200, 1)).toBe(1)
    expect(outputScale(600, 800, 2)).toBe(2)
    const capped = outputScale(899, 40_000, 1)
    expect(capped).toBeLessThan(LOW_DPR_FLOOR)
    expect(899 * 40_000 * capped * capped).toBeLessThanOrEqual(MAX_CANVAS_PIXELS + 1)
  })
})
