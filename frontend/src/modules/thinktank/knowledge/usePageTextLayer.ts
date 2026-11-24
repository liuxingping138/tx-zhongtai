import type { PageViewport, PDFPageProxy, TextLayer } from 'pdfjs-dist'
import type { Ref } from 'vue'

import { buildPageText, findInPage, segmentsByItem, textSource, type PageText } from './pdfSearch'
import { loadPdfJs, type PdfJsLib } from './pdfjs'
import { paintHighlights } from './textHighlight'

export interface PageTextLayerOptions {
  container: Ref<HTMLElement | undefined>
  /** 当前查找词（已 normalizeQuery），空串表示没在查找。 */
  query: () => string
  /** 本页第几处是当前匹配，-1 表示不在本页。 */
  selected: () => number
  /** 当前那处的高亮画好了：交给阅读器滚到它。 */
  onSelected: (el: HTMLElement) => void
  load?: () => Promise<Pick<PdfJsLib, 'TextLayer'>>
}

/**
 * 一页的文字层（PDF.js TextLayer）：透明文字盖在画布上，能选中、复制，查找高亮也画在它上面。
 *
 * - 画布画完才建，不和第一页出图抢时间；只给正在显示的页建（页面移出范围、缩放、换文档时 destroy）。
 * - 建文字层失败不影响画布，只是这页不能选字。
 */
export function usePageTextLayer(options: PageTextLayerOptions) {
  const load = options.load ?? loadPdfJs
  let layer: TextLayer | null = null
  let text: PageText | null = null
  let touched = new Set<number>()
  let seq = 0

  function paint() {
    if (!layer || !text) return
    const query = options.query()
    const matches = query ? findInPage(text, query) : []
    const result = paintHighlights(layer.textDivs, text.items, segmentsByItem(text, matches, options.selected()), touched)
    touched = result.touched
    if (result.selected) options.onSelected(result.selected)
  }

  function destroy() {
    seq += 1
    layer?.cancel()
    layer = null
    text = null
    touched = new Set()
    options.container.value?.replaceChildren()
  }

  async function render(mine: number, page: PDFPageProxy, viewport: PageViewport, el: HTMLElement) {
    const [lib, content] = await Promise.all([load(), page.getTextContent()])
    if (mine !== seq) return
    el.style.setProperty('--scale-factor', String(viewport.scale))
    const next = new lib.TextLayer({ textContentSource: content, container: el, viewport })
    layer = next
    await next.render()
    if (mine !== seq) return
    // 换行标记取自同一份 getTextContent（跳过标记内容后与 textContentItemsStr 一一对应），查找时西文跨行补空格
    text = buildPageText(next.textContentItemsStr, textSource(content.items).eol)
    paint()
  }

  /** 按这一页、这个缩放重建文字层；旧的先拆掉。 */
  async function build(page: PDFPageProxy, viewport: PageViewport): Promise<void> {
    destroy()
    const mine = seq
    const el = options.container.value
    if (!el) return
    try {
      await render(mine, page, viewport, el)
    } catch {
      if (mine === seq) destroy() // 文字层建不出来：画布照常显示，只是这页不能选字
    }
  }

  return { build, paint, destroy }
}
