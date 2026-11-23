// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PdfPageCanvas from './PdfPageCanvas.vue'
import { asPage, fakePage, flush, textLayers, type FakePage } from './pdf.testkit'
import { HIGHLIGHT_CLASS } from './textHighlight'

vi.mock('./pdfjs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./pdfjs')>()
  const kit = await import('./pdf.testkit')
  return { ...actual, loadPdfJs: () => Promise.resolve(kit.fakeLib()) }
})

function mountPage(page: FakePage, props: Record<string, unknown> = {}) {
  return mount(PdfPageCanvas, {
    props: {
      pageNumber: 1,
      scale: 1,
      size: { width: 600, height: 800 },
      active: true,
      generation: 1,
      getPage: () => Promise.resolve(asPage(page)),
      ...props,
    },
  })
}

describe('PdfPageCanvas', () => {
  beforeEach(() => {
    textLayers.length = 0
  })

  it('画布画完再建文字层，量出的尺寸交给阅读器', async () => {
    const page = fakePage()
    const wrapper = mountPage(page)
    await flush()
    expect(page.render).toHaveBeenCalledTimes(1)
    expect(page.getTextContent).toHaveBeenCalledTimes(1)
    expect(wrapper.find('canvas').classes()).toContain('is-ready')
    expect(wrapper.find('.pdf-page__text').text()).toBe('数字政府建设方案')
    expect(wrapper.emitted('measured')?.[0]).toEqual([1, { width: 600, height: 800 }])
    expect(wrapper.find('.pdf-page__hint').exists()).toBe(false)
  })

  it('移出可见范围：拆掉文字层、释放画布和页面数据', async () => {
    const page = fakePage()
    const wrapper = mountPage(page)
    await flush()
    await wrapper.setProps({ active: false })
    await flush()
    expect(textLayers[0]!.cancel).toHaveBeenCalled()
    expect(wrapper.find('.pdf-page__text').text()).toBe('')
    expect(page.cleanup).toHaveBeenCalled()
    expect((wrapper.find('canvas').element as HTMLCanvasElement).width).toBe(0)
    expect(wrapper.find('.pdf-page__hint').text()).toBe('第 1 页')
  })

  it('缩放后按新比例重画并重建文字层；卸载时也拆掉', async () => {
    const page = fakePage()
    const wrapper = mountPage(page)
    await flush()
    await wrapper.setProps({ scale: 2 })
    await flush()
    expect(page.render).toHaveBeenCalledTimes(2)
    expect(textLayers).toHaveLength(2)
    expect(textLayers[0]!.cancel).toHaveBeenCalled()
    expect((wrapper.find('.pdf-page__text').element as HTMLElement).style.getPropertyValue('--scale-factor')).toBe('2')
    wrapper.unmount()
    expect(textLayers[1]!.cancel).toHaveBeenCalled()
  })

  it('查找词和当前那处变化时重画高亮，并报告当前那处', async () => {
    const wrapper = mountPage(fakePage())
    await flush()
    await wrapper.setProps({ query: '政府', selected: 0 })
    await flush()
    expect(wrapper.findAll(`.${HIGHLIGHT_CLASS}`)).toHaveLength(1)
    expect(wrapper.emitted('matchFocus')).toHaveLength(1)
    await wrapper.setProps({ selected: -1 })
    await flush()
    expect(wrapper.find('.is-selected').exists()).toBe(false)
  })

  it('取页失败：显示这页加载失败并上报', async () => {
    const err = new Error('boom')
    const wrapper = mountPage(fakePage(), { getPage: () => Promise.reject(err) })
    await flush()
    expect(wrapper.find('.pdf-page__hint').text()).toBe('第 1 页加载失败')
    expect(wrapper.emitted('failed')?.[0]).toEqual([err])
  })

  it('1x 屏上的窄页按 1.5 倍像素画（双栏预览不发虚）', async () => {
    vi.stubGlobal('devicePixelRatio', 1)
    const page = fakePage()
    const wrapper = mountPage(page)
    await flush()
    const canvas = wrapper.find('canvas').element as HTMLCanvasElement
    expect(canvas.width).toBe(900)
    expect(canvas.height).toBe(1200)
    expect(page.render.mock.calls[0]![0]).toMatchObject({ transform: [1.5, 0, 0, 1.5, 0, 0] })
    vi.unstubAllGlobals()
  })
})
