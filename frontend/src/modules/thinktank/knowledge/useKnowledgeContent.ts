import { ref } from 'vue'

export type PreviewMode = 'pdf' | 'text' | 'summary'

export interface BlobResponse {
  data: Blob
  headers?: Record<string, unknown>
}

interface Entry { mode: PreviewMode; url: string; text: string }
interface CachedEntry { version: string; entry: Entry }

/** 最多留几份原文：退回列表再进同一文件、或上一条/下一条来回看都不再重下。 */
export const CONTENT_CACHE_SIZE = 6

const OFFICE_EXTS = new Set(['PPT', 'PPTX', 'DOC', 'DOCX', 'XLS', 'XLSX', 'WORD', 'EXCEL'])
const sessionCache = new Map<string, CachedEntry>()
let sessionOwner = ''

/** 清空会话级原文缓存并释放全部对象 URL。 */
export function clearKnowledgeContentCache() {
  for (const item of sessionCache.values()) {
    if (item.entry.url) URL.revokeObjectURL(item.entry.url)
  }
  sessionCache.clear()
  sessionOwner = ''
}

/** 和服务端 office_preview.office_extension 同一口径：要经 LibreOffice 转 PDF 的，首次打开要等几秒。 */
export function isOfficeFile(fileName: string, suffix: string): boolean {
  const ext = /\.([^.]+)$/.exec(fileName || '')?.[1]?.toUpperCase() ?? ''
  return OFFICE_EXTS.has(ext) || OFFICE_EXTS.has((suffix || '').toUpperCase())
}

export interface KnowledgeContentOptions {
  persistent?: boolean
  getOwner?: () => string
}

function evictOverflow(cache: Map<string, CachedEntry>, protectedId: string) {
  for (const key of cache.keys()) {
    if (cache.size <= CONTENT_CACHE_SIZE) break
    if (key === protectedId) continue
    const url = cache.get(key)?.entry.url
    if (url) URL.revokeObjectURL(url)
    cache.delete(key)
  }
}

function revokeKey(cache: Map<string, CachedEntry>, id: string) {
  const existing = cache.get(id)
  if (existing?.entry.url) URL.revokeObjectURL(existing.entry.url)
  cache.delete(id)
}

/**
 * 预览页右栏的原文：PDF 用对象 URL 内嵌，文本直接显示，取不到回退摘要。
 *
 * - 同一条记录同时只发一次 `/content`；换到别的记录时中止还在路上的请求。
 * - `persistent: true` 时使用当前登录会话级内存缓存（按用户 ID 隔离、按文件版本失效，
 *   每次进页仍先过 `/preview` 实时鉴权），退回列表再进同一文件可 0 传输秒开。
 */
export function useKnowledgeContent(
  fetchBlob: (id: string, signal?: AbortSignal) => Promise<BlobResponse>,
  onError: (err: unknown) => void,
  options: KnowledgeContentOptions = {},
) {
  const loading = ref(false)
  const mode = ref<PreviewMode>('summary')
  const text = ref('')
  const pdfUrl = ref('')
  const cache = options.persistent ? sessionCache : new Map<string, CachedEntry>()
  let seq = 0
  let shownId = ''
  let pending: { id: string; ctrl: AbortController; promise: Promise<Entry> } | null = null

  function syncOwner() {
    if (!options.persistent || !options.getOwner) return
    const currentOwner = options.getOwner()
    if (!currentOwner || (sessionOwner && sessionOwner !== currentOwner)) {
      clearKnowledgeContentCache()
    }
    sessionOwner = currentOwner
  }

  function remember(id: string, version: string, entry: Entry) {
    const prev = cache.get(id)
    if (prev && prev.entry.url && prev.entry.url !== entry.url) URL.revokeObjectURL(prev.entry.url)
    cache.delete(id)
    cache.set(id, { version, entry })
    evictOverflow(cache, shownId)
  }

  async function toEntry(want: 'pdf' | 'text', resp: BlobResponse): Promise<Entry> {
    const ct = String((resp.headers?.['content-type'] as string | undefined) || resp.data.type || '').toLowerCase()
    if (want === 'pdf' && ct.includes('pdf')) return { mode: 'pdf', url: URL.createObjectURL(resp.data), text: '' }
    return { mode: want === 'pdf' ? 'summary' : want, url: '', text: await resp.data.text() }
  }

  function request(id: string, want: 'pdf' | 'text', version: string): Promise<Entry> {
    if (pending?.id === id) return pending.promise
    pending?.ctrl.abort()
    const ctrl = new AbortController()
    const promise = fetchBlob(id, ctrl.signal)
      .then((resp) => {
        if (ctrl.signal.aborted) throw new DOMException('Aborted', 'AbortError')
        return toEntry(want, resp)
      })
      .then((entry) => { remember(id, version, entry); return entry })
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

  /** 主动踢出某条缓存（如删除文件、鉴权失败）。 */
  function evict(id: string) {
    revokeKey(cache, id)
  }

  function abortOther(id: string) {
    if (pending && pending.id !== id) {
      pending.ctrl.abort()
      pending = null
    }
  }

  function tryCached(id: string, version: string): boolean {
    const hit = cache.get(id)
    if (!hit || hit.version !== version) return false
    remember(id, version, hit.entry)
    display(hit.entry)
    return true
  }

  /** 显示一条记录：先用接口给的模式和摘要，有源文件再取原文（版本一致直接命中缓存）。 */
  async function show(id: string, initialMode: PreviewMode, summary: string, hasBinary: boolean, version = '') {
    syncOwner()
    seq += 1
    const mine = seq
    abortOther(id)
    shownId = id
    mode.value = initialMode
    text.value = summary
    pdfUrl.value = ''
    loading.value = false
    if (!hasBinary || initialMode === 'summary' || tryCached(id, version)) return
    loading.value = true
    try {
      const entry = await request(id, initialMode, version)
      if (mine === seq) display(entry)
    } catch (err) {
      if (mine === seq) { mode.value = 'summary'; onError(err) }
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  /** 离开页面：中止在途请求；非会话级缓存同步释放全部对象 URL。 */
  function dispose() {
    cancel()
    if (options.persistent) return
    for (const item of cache.values()) if (item.entry.url) URL.revokeObjectURL(item.entry.url)
    cache.clear()
  }

  return { loading, mode, text, pdfUrl, show, cancel, evict, dispose }
}
