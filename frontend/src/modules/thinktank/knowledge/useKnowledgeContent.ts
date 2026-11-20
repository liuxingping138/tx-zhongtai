import { ref } from 'vue'

export type PreviewMode = 'pdf' | 'text' | 'summary'

export interface BlobResponse {
  data: Blob
  headers?: Record<string, unknown>
}

interface Entry { mode: PreviewMode; url: string; text: string }

/** 这一页里最多留几份原文：上一条 / 下一条来回看不再重下、重转码。 */
export const CONTENT_CACHE_SIZE = 6

const OFFICE_EXTS = new Set(['PPT', 'PPTX', 'DOC', 'DOCX', 'XLS', 'XLSX', 'WORD', 'EXCEL'])

/** 和服务端 office_preview.office_extension 同一口径：要经 LibreOffice 转 PDF 的，首次打开要等几秒。 */
export function isOfficeFile(fileName: string, suffix: string): boolean {
  const ext = /\.([^.]+)$/.exec(fileName || '')?.[1]?.toUpperCase() ?? ''
  return OFFICE_EXTS.has(ext) || OFFICE_EXTS.has((suffix || '').toUpperCase())
}

/**
 * 预览页右栏的原文：PDF 用对象 URL 内嵌，文本直接显示，取不到回退摘要。
 *
 * - 同一条记录同时只发一次 `/content`；换到别的记录时中止还在路上的请求（服务端随之停掉转码），
 *   晚到的旧结果只会被丢掉，不会盖掉新记录的内容。
 * - 取到的原文按最近使用留 {@link CONTENT_CACHE_SIZE} 份，挤出去的释放对象 URL。
 *   缓存只活在这一页：离开预览页（{@link dispose}）全部释放，接口本身仍是 no-store，撤权后重新进页就看不到。
 */
export function useKnowledgeContent(
  fetchBlob: (id: string, signal?: AbortSignal) => Promise<BlobResponse>,
  onError: (err: unknown) => void,
) {
  const loading = ref(false)
  const mode = ref<PreviewMode>('summary')
  const text = ref('')
  const pdfUrl = ref('')
  const cache = new Map<string, Entry>()
  let seq = 0
  let shownId = ''
  let pending: { id: string; ctrl: AbortController; promise: Promise<Entry> } | null = null

  function remember(id: string, entry: Entry) {
    cache.delete(id)
    cache.set(id, entry)
    for (const key of cache.keys()) {
      if (cache.size <= CONTENT_CACHE_SIZE) break
      if (key === shownId) continue
      const url = cache.get(key)?.url
      if (url) URL.revokeObjectURL(url)
      cache.delete(key)
    }
  }

  async function toEntry(want: 'pdf' | 'text', resp: BlobResponse): Promise<Entry> {
    const ct = String((resp.headers?.['content-type'] as string | undefined) || resp.data.type || '').toLowerCase()
    if (want === 'pdf' && ct.includes('pdf')) return { mode: 'pdf', url: URL.createObjectURL(resp.data), text: '' }
    // 要 PDF 却拿到文本：服务端转不出来回的是摘要
    return { mode: want === 'pdf' ? 'summary' : want, url: '', text: await resp.data.text() }
  }

  function request(id: string, want: 'pdf' | 'text'): Promise<Entry> {
    if (pending?.id === id) return pending.promise
    pending?.ctrl.abort()
    const ctrl = new AbortController()
    const promise = fetchBlob(id, ctrl.signal)
      .then((resp) => {
        // 中止前已经到了的响应也不要：不建对象 URL、不进缓存
        if (ctrl.signal.aborted) throw new DOMException('Aborted', 'AbortError')
        return toEntry(want, resp)
      })
      .then((entry) => { remember(id, entry); return entry })
      .finally(() => { if (pending?.promise === promise) pending = null })
    pending = { id, ctrl, promise }
    return promise
  }

  function display(entry: Entry) {
    mode.value = entry.mode
    pdfUrl.value = entry.url
    if (entry.mode !== 'pdf') text.value = entry.text
  }

  /** 作废显示中的内容、中止还在路上的请求；换记录前调。缓存留着。 */
  function cancel() {
    seq += 1
    shownId = ''
    pending?.ctrl.abort()
    pending = null
    pdfUrl.value = ''
    loading.value = false
  }

  /** 显示一条记录：先用接口给的模式和摘要，有源文件再取原文（缓存里有就直接用）。 */
  async function show(id: string, initialMode: PreviewMode, summary: string, hasBinary: boolean) {
    seq += 1
    const mine = seq
    if (pending && pending.id !== id) { pending.ctrl.abort(); pending = null }
    shownId = id
    mode.value = initialMode
    text.value = summary
    pdfUrl.value = ''
    loading.value = false
    if (!hasBinary || initialMode === 'summary') return
    const hit = cache.get(id)
    if (hit) { remember(id, hit); display(hit); return }
    loading.value = true
    try {
      const entry = await request(id, initialMode)
      if (mine === seq) display(entry)
    } catch (err) {
      if (mine === seq) { mode.value = 'summary'; onError(err) }
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  /** 离开页面：中止请求、释放全部对象 URL。 */
  function dispose() {
    cancel()
    for (const entry of cache.values()) if (entry.url) URL.revokeObjectURL(entry.url)
    cache.clear()
  }

  return { loading, mode, text, pdfUrl, show, cancel, dispose }
}
