import { splitBySegments, type Segment } from './pdfSearch'

export const HIGHLIGHT_CLASS = 'pdf-hl'
export const SELECTED_CLASS = 'is-selected'

/**
 * 在 PDF.js 文字层的文字块上画查找高亮：命中的块把文字切成「普通文字 + 高亮 span」，
 * 上次画过、这次不再命中的块还原成纯文字。返回这次改过的块（下次还原用）和当前那处的高亮元素。
 *
 * 只改块的子节点、不动块本身的位置和变换，文字照样能选中复制。
 */
export function paintHighlights(
  divs: readonly HTMLElement[],
  items: readonly string[],
  segments: ReadonlyMap<number, Segment[]>,
  touched: ReadonlySet<number>,
): { touched: Set<number>; selected: HTMLElement | null } {
  for (const item of touched) {
    const div = divs[item]
    if (div && !segments.has(item)) div.textContent = items[item] ?? ''
  }
  let selected: HTMLElement | null = null
  for (const [item, list] of segments) {
    const div = divs[item]
    if (!div) continue
    const doc = div.ownerDocument
    const nodes = splitBySegments(items[item] ?? '', list).map(([text, segment]) => {
      if (!segment) return doc.createTextNode(text)
      const span = doc.createElement('span')
      span.className = segment.selected ? `${HIGHLIGHT_CLASS} ${SELECTED_CLASS}` : HIGHLIGHT_CLASS
      span.textContent = text
      if (segment.selected) selected ??= span
      return span
    })
    div.replaceChildren(...nodes)
  }
  return { touched: new Set(segments.keys()), selected }
}
