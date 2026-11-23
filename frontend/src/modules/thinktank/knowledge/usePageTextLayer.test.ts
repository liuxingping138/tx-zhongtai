// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { asPage, fakeLib, fakePage, fakeViewport, flush, textLayers } from './pdf.testkit'
import { HIGHLIGHT_CLASS, SELECTED_CLASS } from './textHighlight'
import { usePageTextLayer } from './usePageTextLayer'

function setup(overrides: { query?: string; selected?: number; load?: () => Promise<never> } = {}) {
  const container = ref<HTMLElement | undefined>(document.createElement('div'))
  const state = { query: overrides.query ?? '', selected: overrides.selected ?? -1 }
  const onSelected = vi.fn()
  const layer = usePageTextLayer({
    container,
    query: () => state.query,
    selected: () => state.selected,
    onSelected,
    load: overrides.load ?? (() => Promise.resolve(fakeLib())),
  })
  return { layer, container, state, onSelected }
}

describe('usePageTextLayer', () => {
  beforeEach(() => { textLayers.length = 0 })

  it('建文字层：按缩放设好 --scale-factor，透明文字块可选中', async () => {
    const { layer, container } = setup()
    const page = fakePage()
    await layer.build(asPage(page), fakeViewport(1.5))
    expect(page.getTextContent).toHaveBeenCalledTimes(1)
    expect(container.value!.style.getPropertyValue('--scale-factor')).toBe('1.5')
    expect(container.value!.textContent).toBe('数字政府建设方案')
    expect(textLayers).toHaveLength(1)
  })

  it('画查找高亮，当前那处交给阅读器；查找词变了重画', async () => {
    const { layer, container, state, onSelected } = setup({ query: '政府', selected: 0 })
    await layer.build(asPage(fakePage()), fakeViewport(1))
    const hl = container.value!.querySelector(`.${HIGHLIGHT_CLASS}`)
    expect(hl?.classList.contains(SELECTED_CLASS)).toBe(true)
    expect(onSelected).toHaveBeenCalledWith(hl)

    state.query = ''
    layer.paint()
    expect(container.value!.querySelector(`.${HIGHLIGHT_CLASS}`)).toBeNull()
    expect(container.value!.textContent).toBe('数字政府建设方案')
  })

  it('重建、拆掉时 cancel 旧文字层、清空容器；拆掉后的迟到结果不再画', async () => {
    const { layer, container } = setup()
    await layer.build(asPage(fakePage()), fakeViewport(1))
    await layer.build(asPage(fakePage(['第二次'])), fakeViewport(2))
    expect(textLayers[0]!.cancel).toHaveBeenCalled()
    expect(container.value!.textContent).toBe('第二次')

    const slow = layer.build(asPage(fakePage(['迟到'])), fakeViewport(1))
    layer.destroy()
    await slow
    await flush()
    expect(container.value!.textContent).toBe('')
    layer.paint() // 没有文字层时什么也不做
  })

  it('PDF.js 加载失败或没有容器：不抛错，画布照常显示', async () => {
    const failing = setup({ load: () => Promise.reject(new Error('chunk')) })
    await expect(failing.layer.build(asPage(fakePage()), fakeViewport(1))).resolves.toBeUndefined()
    expect(failing.container.value!.textContent).toBe('')

    const detached = setup()
    detached.container.value = undefined
    const page = fakePage()
    await detached.layer.build(asPage(page), fakeViewport(1))
    expect(page.getTextContent).not.toHaveBeenCalled()
  })
})
