// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'

import { HIGHLIGHT_CLASS, paintHighlights, SELECTED_CLASS } from './textHighlight'

function divs(items: string[]): HTMLElement[] {
  return items.map((text) => {
    const span = document.createElement('span')
    span.textContent = text
    return span
  })
}

describe('paintHighlights', () => {
  it('命中的块切成普通文字和高亮 span，当前那处单独标出', () => {
    const items = ['数字政府', '政府']
    const els = divs(items)
    const segments = new Map([
      [0, [{ from: 2, to: 4, selected: true }]],
      [1, [{ from: 0, to: 2, selected: false }]],
    ])
    const result = paintHighlights(els, items, segments, new Set())
    expect(els[0]!.innerHTML).toBe(`数字<span class="${HIGHLIGHT_CLASS} ${SELECTED_CLASS}">政府</span>`)
    expect(els[1]!.innerHTML).toBe(`<span class="${HIGHLIGHT_CLASS}">政府</span>`)
    expect(result.selected?.textContent).toBe('政府')
    expect(result.selected?.classList.contains(SELECTED_CLASS)).toBe(true)
    expect([...result.touched]).toEqual([0, 1])
    // 文字内容不变：选中复制得到的仍是原文
    expect(els.map(el => el.textContent)).toEqual(items)
  })

  it('上次画过、这次不再命中的块还原成纯文字；越界的块跳过', () => {
    const items = ['数字政府', '政府']
    const els = divs(items)
    const first = paintHighlights(els, items, new Map([[0, [{ from: 0, to: 2, selected: false }]]]), new Set())
    const second = paintHighlights(els, items, new Map([[9, [{ from: 0, to: 1, selected: true }]]]), new Set([...first.touched, 7]))
    expect(els[0]!.innerHTML).toBe('数字政府')
    expect(second.selected).toBeNull()
    expect([...second.touched]).toEqual([9])
  })
})
