/** 组件单测共用的 PDF.js 替身：只实现阅读器用到的那几个方法。 */
import type { PageViewport, PDFPageProxy } from 'pdfjs-dist'
import { vi, type Mock } from 'vitest'

import type { PdfJsLib } from './pdfjs'

/** 记下建过的文字层：测试据此看建了几次、有没有被 cancel。 */
export const textLayers: FakeTextLayer[] = []

export class FakeTextLayer {
  textDivs: HTMLElement[] = []
  textContentItemsStr: string[] = []
  cancel: Mock<() => void> = vi.fn()
  private readonly container: HTMLElement
  private readonly items: string[]

  constructor({ textContentSource, container }: { textContentSource: { items: Array<{ str: string }> }; container: HTMLElement }) {
    this.container = container
    this.items = textContentSource.items.map(item => item.str)
    textLayers.push(this)
  }

  render(): Promise<void> {
    for (const str of this.items) {
      const span = this.container.ownerDocument.createElement('span')
      span.textContent = str
      this.container.append(span)
      this.textDivs.push(span)
      this.textContentItemsStr.push(str)
    }
    return Promise.resolve()
  }
}

export function fakeViewport(scale: number, width = 600, height = 800): PageViewport {
  return { scale, width: width * scale, height: height * scale } as unknown as PageViewport
}

export interface FakePage {
  getViewport: Mock<(params: { scale: number }) => PageViewport>
  getTextContent: Mock<() => Promise<{ items: Array<{ str: string }> }>>
  render: Mock<(params: Record<string, unknown>) => { promise: Promise<void>; cancel: () => void }>
  cleanup: Mock<() => void>
}

export function fakePage(items: string[] = ['数字政府', '建设方案']): FakePage {
  return {
    getViewport: vi.fn(({ scale }: { scale: number }) => fakeViewport(scale)),
    getTextContent: vi.fn(() => Promise.resolve({ items: items.map(str => ({ str })) })),
    render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
    cleanup: vi.fn(),
  }
}

export function asPage(page: FakePage): PDFPageProxy {
  return page as unknown as PDFPageProxy
}

export function fakeLib(getDocument?: unknown): Pick<PdfJsLib, 'TextLayer' | 'getDocument'> {
  return { TextLayer: FakeTextLayer, getDocument } as unknown as Pick<PdfJsLib, 'TextLayer' | 'getDocument'>
}

/** 等 Promise 链和 Vue 的更新都跑完。 */
export async function flush(rounds = 6): Promise<void> {
  for (let i = 0; i < rounds; i += 1) await new Promise(resolve => setTimeout(resolve, 0))
}
