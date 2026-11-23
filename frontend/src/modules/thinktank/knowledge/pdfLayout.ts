/** PDF 预览的缩放、页码和按需渲染范围：纯计算，组件里只管 DOM。 */

export interface PageSize {
  width: number
  height: number
}

/** A4（PDF 点）：第一页的尺寸到手前，占位先按它算。 */
export const DEFAULT_PAGE_SIZE: PageSize = { width: 595, height: 842 }
export const ZOOM_STEPS = [0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3] as const
export const MIN_SCALE = 0.5
export const MAX_SCALE = 3
/** 页面左右留白（px），适合宽度时要扣掉，否则会出横向滚动条。 */
export const VIEW_GUTTER = 16
/** 可见页上下各多渲染几页：慢慢往下翻时下一页已经画好，又不至于 55 页全留着画布。 */
export const RENDER_BUFFER = 2
/** 单张画布最多这么多像素（约 64MB 显存）：放大到 300% 又是高清屏时按它降低清晰度，不至于画布建不出来。 */
export const MAX_CANVAS_PIXELS = 16_777_216

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

export function clampScale(scale: number): number {
  return clamp(Number.isFinite(scale) ? scale : 1, MIN_SCALE, MAX_SCALE)
}

/** 适合宽度：页面宽度刚好铺满容器（扣掉两边留白）。容器还没量出来时按 100%。 */
export function fitWidthScale(containerWidth: number, pageWidth: number): number {
  if (containerWidth <= 0 || pageWidth <= 0) return 1
  return clampScale((containerWidth - VIEW_GUTTER * 2) / pageWidth)
}

/** 放大、缩小走到下一档；当前值落在两档之间（如适合宽度算出的 1.37）时走到相邻那档。 */
export function stepZoom(current: number, direction: 1 | -1): number {
  if (direction > 0) return ZOOM_STEPS.find(step => step > current + 0.001) ?? MAX_SCALE
  return [...ZOOM_STEPS].reverse().find(step => step < current - 0.001) ?? MIN_SCALE
}

export function zoomLabel(scale: number): string {
  return `${Math.round(scale * 100)}%`
}

/** 页码跳转：非数字回到当前页，超出范围夹到首尾。 */
export function clampPage(page: number, total: number, fallback = 1): number {
  if (total <= 0) return 1
  if (!Number.isFinite(page)) return clamp(fallback, 1, total)
  return clamp(Math.round(page), 1, total)
}

/** 要渲染（保留画布）的页：可见页加上下缓冲；其余页只留占位尺寸，画布释放。 */
export function pagesToRender(visible: Iterable<number>, total: number, buffer = RENDER_BUFFER): Set<number> {
  const out = new Set<number>()
  for (const page of visible) {
    for (let n = page - buffer; n <= page + buffer; n += 1) {
      if (n >= 1 && n <= total) out.add(n)
    }
  }
  return out
}

/** 当前页：可见比例最大的那页，一样大时取靠前的；没有可见页时保持原值。 */
export function mostVisiblePage(ratios: ReadonlyMap<number, number>, current: number): number {
  let best = current
  let bestRatio = 0
  for (const [page, ratio] of ratios) {
    if (ratio > bestRatio || (ratio === bestRatio && ratio > 0 && page < best)) {
      best = page
      bestRatio = ratio
    }
  }
  return best
}

/** 画布的像素倍数：跟着设备像素比画得清楚，但不超过 MAX_CANVAS_PIXELS。 */
export function outputScale(cssWidth: number, cssHeight: number, devicePixelRatio: number): number {
  const ratio = devicePixelRatio > 0 ? devicePixelRatio : 1
  const area = cssWidth * cssHeight
  if (area <= 0) return ratio
  return Math.min(ratio, Math.sqrt(MAX_CANVAS_PIXELS / area))
}
