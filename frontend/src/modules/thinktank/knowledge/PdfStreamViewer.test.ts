// @vitest-environment happy-dom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PdfStreamViewer from './PdfStreamViewer.vue'
import { fakeLib, fakePage, flush, textLayers, type FakePage } from './pdf.testkit'
import { SEARCH_DEBOUNCE_MS } from './usePdfSearch'

const NUM_PAGES = 20
let pages: FakePage[] = []
const getPage = vi.fn((n: number) => Promise.resolve(pages[n - 1]!))
const getDocument = vi.fn(() => ({
  promise: Promise.resolve({ numPages: NUM_PAGES, getPage }),
  destroy: vi.fn(() => Promise.resolve()),
}))

vi.mock('@/api/http', () => ({ afterRefreshFailure: (err: unknown) => err }))
vi.mock('@/api/session', () => ({ getAccessToken: () => 't1', refreshSession: () => Promise.resolve() }))
vi.mock('./pdfjs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./pdfjs')>()
  return { ...actual, loadPdfJs: () => Promise.resolve(fakeLib(getDocument)) }
})

/** 可见性观察的替身：测试手动告诉阅读器哪几页露出来了。 */
class FakeIntersectionObserver {
  static last: FakeIntersectionObserver | null = null
  targets: Element[] = []
  constructor(private readonly callback: IntersectionObserverCallback) {
    FakeIntersectionObserver.last = this
  }
  observe(el: Element) { this.targets.push(el) }
  disconnect() { this.targets = [] }
  show(pageNumbers: number[]) {
    const entries = this.targets
      .filter(el => pageNumbers.includes(Number((el as HTMLElement).dataset.page)))
      .map(target => ({ target, isIntersecting: true, intersectionRatio: 1 }) as unknown as IntersectionObserverEntry)
    this.callback(entries, this as unknown as IntersectionObserver)
  }
}

const stubs = { 'el-icon': true, 'el-alert': true, 'el-button': true }
let wrapper: VueWrapper | null = null

async function open(): Promise<VueWrapper> {
  wrapper = mount(PdfStreamViewer, { props: { url: '/content' }, global: { stubs }, attachTo: document.body })
  await flush()
  FakeIntersectionObserver.last?.show([1])
  await flush()
  return wrapper
}

function textFetches(): number[] {
  return pages.flatMap((page, i) => (page.getTextContent.mock.calls.length ? [i + 1] : []))
}

describe('PdfStreamViewer', () => {
  beforeEach(() => {
    pages = Array.from({ length: NUM_PAGES }, (_, i) => fakePage(i === 14 ? ['第十五页提到数字政府'] : [`第${i + 1}页`]))
    getPage.mockClear()
    textLayers.length = 0
    vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver)
  })
  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.unstubAllGlobals()
  })

  it('打开只画可见页和上下缓冲，没查找时其余页一页文字都不取', async () => {
    const view = await open()
    expect(view.findAll('[data-page]')).toHaveLength(NUM_PAGES)
    expect(textFetches()).toEqual([1, 2, 3])
    expect(getPage.mock.calls.every(([n]) => n <= 3)).toBe(true)
    expect(view.find('.pdf-search').exists()).toBe(false)
  })

  it('点查找打开查找条；输入后才逐页取文字，跳到匹配的那页并高亮', async () => {
    const view = await open()
    await view.find('button[aria-label="查找"]').trigger('click')
    expect(view.find('.pdf-search').exists()).toBe(true)
    expect(document.activeElement).toBe(view.find('.pdf-search__input').element)
    expect(textFetches()).toEqual([1, 2, 3])

    await view.find('.pdf-search__input').setValue('数字政府')
    await new Promise(resolve => setTimeout(resolve, SEARCH_DEBOUNCE_MS + 20))
    await flushPromises()
    await flush()
    expect(textFetches()).toHaveLength(NUM_PAGES)
    expect(view.find('.pdf-search__count').text()).toBe('第 1 / 1 处')

    FakeIntersectionObserver.last?.show([15])
    await flush()
    expect(view.find('[data-page="15"] .pdf-hl.is-selected').text()).toBe('数字政府')
  })

  it('Esc 先关查找条、清掉高亮，焦点回到文档；Ctrl+F 在文档里重新打开', async () => {
    const view = await open()
    await view.find('.pdf-viewer').trigger('keydown', { key: 'f', ctrlKey: true })
    const input = view.find('.pdf-search__input')
    expect(input.exists()).toBe(true)
    await input.trigger('keydown', { key: 'Escape' })
    expect(view.find('.pdf-search').exists()).toBe(false)
    expect(document.activeElement).toBe(view.find('.pdf-viewer__scroll').element)

    const exposed = view.vm as unknown as { openSearch: () => void; closeSearch: () => boolean }
    expect(exposed.closeSearch()).toBe(false)
    exposed.openSearch()
    await flush()
    expect(view.find('.pdf-search').exists()).toBe(true)
    expect(exposed.closeSearch()).toBe(true)
  })

  it('工具栏：放大缩小、100%、适合宽度、翻页', async () => {
    const view = await open()
    const zoom = () => view.find('.pdf-viewer__zoom').text()
    await view.find('button[title="放大"]').trigger('click')
    const bigger = zoom()
    await view.find('button[title="缩小"]').trigger('click')
    expect(zoom()).not.toBe(bigger)
    const [fit, actual] = view.findAll('.pdf-viewer__btn--text')
    await actual!.trigger('click')
    expect(zoom()).toBe('100%')
    expect(actual!.classes()).toContain('is-active')
    await fit!.trigger('click')
    expect(fit!.classes()).toContain('is-active')

    expect(view.find('button[title="上一页"]').attributes('disabled')).toBeDefined()
    await view.find('button[title="下一页"]').trigger('click')
    expect((view.find('.pdf-viewer__page-input').element as HTMLInputElement).value).toBe('2')
  })
})
