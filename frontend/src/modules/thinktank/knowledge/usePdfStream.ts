import type { PDFDocumentLoadingTask, PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
import { ref, shallowRef } from 'vue'

import { DEFAULT_PAGE_SIZE, type PageSize } from './pdfLayout'
import { documentOptions, isCancelled, isInvalidPdf, responseStatus, type PdfJsLib } from './pdfjs'

/** idle 没有文档；invalid 拿到的不是 PDF（服务端回了摘要文本），由上层改用文本显示。 */
export type PdfStatus = 'idle' | 'loading' | 'ready' | 'error' | 'invalid'

export interface PdfStreamDeps {
  load: () => Promise<Pick<PdfJsLib, 'getDocument'>>
  getToken: () => string
  /** 续期访问令牌；被拒或连不上时抛错。 */
  refresh: () => Promise<unknown>
}

const HTTP_UNAUTHORIZED = 401

/** 被后一次打开取代：按 PDF.js 的取消处理，不显示成错误。 */
function superseded(): Error {
  const err = new Error('superseded')
  err.name = 'AbortException'
  return err
}

function failureText(err: unknown): string {
  const status = responseStatus(err)
  if (status === 403) return '没有权限查看这份原文'
  if (status === HTTP_UNAUTHORIZED) return '登录已失效，请重新登录后再看'
  if (status === 404) return '原文不存在或已被删除'
  if (status !== null && status >= 500) return '文件服务暂时不可用，请稍后重试'
  return '原文加载失败，请重试'
}

/**
 * 按 Range 分段读一份 PDF：PDF.js 只取当前要画的页用到的那几段。
 *
 * - 打开时用当前令牌；PDF.js 打开后请求头就定了，所以收到 401 时续期一次、用新令牌重新打开（只重试一次）。
 *   之后某页取数 401（令牌在看的过程中过期）同样续期后重开，页码由调用方保留。
 * - 换文档、离开页面立即 destroy：中止还在路上的 Range 请求，释放 worker 里的文档。
 */
export function usePdfStream(deps: PdfStreamDeps) {
  const status = ref<PdfStatus>('idle')
  const errorText = ref('')
  const numPages = ref(0)
  const baseSize = ref<PageSize>({ ...DEFAULT_PAGE_SIZE })
  const doc = shallowRef<PDFDocumentProxy | null>(null)
  /** 每打开一次加一：页面组件据此丢掉上一份文档的渲染结果。 */
  const generation = ref(0)
  let task: PDFDocumentLoadingTask | null = null
  let seq = 0
  let url = ''
  let reloading: Promise<void> | null = null

  async function release() {
    const oldTask = task
    task = null
    doc.value = null
    numPages.value = 0
    // loadingTask.destroy 中止在途的 Range 请求，连带销毁已打开的文档和 worker 里的数据；失败也不影响换下一份。
    await oldTask?.destroy().catch(() => undefined)
  }

  async function attempt(target: string, mine: number): Promise<PDFDocumentProxy> {
    const lib = await deps.load()
    // 加载 PDF.js 的这段时间里又换了记录：不再建文档，否则没人销毁它
    if (mine !== seq) throw superseded()
    task = lib.getDocument(documentOptions(target, deps.getToken()))
    return task.promise
  }

  async function openWithRefresh(target: string, mine: number): Promise<PDFDocumentProxy> {
    try {
      return await attempt(target, mine)
    } catch (err) {
      if (mine !== seq || responseStatus(err) !== HTTP_UNAUTHORIZED) throw err
      await deps.refresh()
      return attempt(target, mine)
    }
  }

  function fail(err: unknown) {
    if (isCancelled(err)) return
    status.value = isInvalidPdf(err) ? 'invalid' : 'error'
    errorText.value = failureText(err)
  }

  async function settle(pdf: PDFDocumentProxy, mine: number) {
    doc.value = pdf
    const first = await pdf.getPage(1)
    if (mine !== seq) return
    const viewport = first.getViewport({ scale: 1 })
    baseSize.value = { width: viewport.width, height: viewport.height }
    numPages.value = pdf.numPages
    generation.value += 1
    status.value = 'ready'
  }

  /** 打开一份文档（空串表示关掉）。同一时刻只认最后一次调用。 */
  async function open(target: string): Promise<void> {
    const mine = ++seq
    url = target
    errorText.value = ''
    status.value = target ? 'loading' : 'idle'
    await release()
    if (mine !== seq || !target) return
    try {
      const pdf = await openWithRefresh(target, mine)
      if (mine !== seq) return
      await settle(pdf, mine)
    } catch (err) {
      if (mine === seq) fail(err)
    }
  }

  function getPage(pageNumber: number): Promise<PDFPageProxy> | null {
    return doc.value ? doc.value.getPage(pageNumber) : null
  }

  /** 某页的文字块（和文字层同一份 getTextContent，下标一一对应）：只在查找时才调，按需取那一页的数据。 */
  async function getPageText(pageNumber: number): Promise<string[] | null> {
    const pdf = doc.value
    if (!pdf) return null
    const content = await (await pdf.getPage(pageNumber)).getTextContent()
    return content.items.flatMap(item => ('str' in item ? [item.str] : []))
  }

  /** 某页取数或渲染失败：401 说明令牌在看的过程中过期了，续期后重开；其他错误留给那一页自己显示。 */
  async function onPageError(err: unknown): Promise<boolean> {
    if (responseStatus(err) !== HTTP_UNAUTHORIZED || !url) return false
    reloading ??= deps
      .refresh()
      .then(() => open(url))
      .catch((refreshErr: unknown) => fail(refreshErr))
      .finally(() => { reloading = null })
    await reloading
    return true
  }

  function retry(): Promise<void> {
    return open(url)
  }

  /** 离开页面：中止在途请求、释放文档。 */
  async function close(): Promise<void> {
    seq += 1
    url = ''
    status.value = 'idle'
    await release()
  }

  return { status, errorText, numPages, baseSize, doc, generation, open, retry, getPage, getPageText, onPageError, close }
}
