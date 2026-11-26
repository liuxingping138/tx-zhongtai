import { ref } from 'vue'

import { onAccessTokenChange } from '@/api/session'

export type PreviewMode = 'pdf' | 'text' | 'summary'

export interface BlobResponse {
  data: Blob
  headers?: Record<string, unknown>
}

interface TextEntry { mode: 'text' | 'summary'; text: string }
interface CachedEntry { version: string; entry: TextEntry }

/** 文本原文最多留几份：退回列表再进同一文件、或上一条/下一条来回看都不再重下。 */
export const CONTENT_CACHE_SIZE = 6

const OFFICE_EXTS = new Set(['PPT', 'PPTX', 'DOC', 'DOCX', 'XLS', 'XLSX', 'WORD', 'EXCEL'])
const sessionCache = new Map<string, CachedEntry>()
let sessionOwner = ''

/** 清空会话级的文本原文缓存。 */
export function clearKnowledgeContentCache() {
  sessionCache.clear()
  sessionOwner = ''
}

onAccessTokenChange((token) => {
  if (!token) clearKnowledgeContentCache()
})

/** 和服务端 office_preview.office_extension 同一口径：要经 LibreOffice 转 PDF 的，首次打开要等几秒。 */
export function isOfficeFile(fileName: string, suffix: string): boolean {
  const ext = /\.([^.]+)$/.exec(fileName || '')?.[1]?.toUpperCase() ?? ''
  return OFFICE_EXTS.has(ext) || OFFICE_EXTS.has((suffix || '').toUpperCase())
}

/** PDF.js 按 Range 直接读的地址（经网关，和 http 实例同一个 /api/v1 前缀）。 */
export function knowledgeContentUrl(id: string): string {
  return `/api/v1/thinktank/knowledge/${encodeURIComponent(id)}/content`
}

export interface KnowledgeContentOptions {
  persistent?: boolean
  getOwner?: () => string
}

function evictOverflow(cache: Map<string, CachedEntry>, protectedId: string) {
  for (const key of cache.keys()) {
    if (cache.size <= CONTENT_CACHE_SIZE) break
    if (key !== protectedId) cache.delete(key)
  }
}

/**
 * 预览页右栏的原文。
 *
 * - PDF（含 Office 转出的）不在这里下载：只给出 `/content` 地址，由 PDF.js 按 Range 分段取，第一页先出来。
 *   服务端回的其实是摘要文本（转码失败、源文件不存在）时，阅读器报 `unavailable`，再调 `fallbackToText` 按文本取。
 * - 文本（TXT / MD / CSV）整份取回显示。同一条记录同时只发一次 `/content`；换到别的记录时中止还在路上的请求。
 * - `persistent: true` 时文本用当前登录会话级内存缓存（按用户 ID 隔离、按文件版本失效，
 *   每次进页仍先过 `/preview` 实时鉴权）。
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
  let shownVersion = ''
  let pending: { id: string; ctrl: AbortController; promise: Promise<TextEntry> } | null = null

  function syncOwner() {
    if (!options.persistent || !options.getOwner) return
    const currentOwner = options.getOwner()
    if (!currentOwner || (sessionOwner && sessionOwner !== currentOwner)) clearKnowledgeContentCache()
    sessionOwner = currentOwner
  }

  function remember(id: string, version: string, entry: TextEntry) {
    cache.delete(id)
    cache.set(id, { version, entry })
    evictOverflow(cache, shownId)
  }

  async function toEntry(want: 'text' | 'summary', resp: BlobResponse): Promise<TextEntry> {
    const ct = String((resp.headers?.['content-type'] as string | undefined) || resp.data.type || '').toLowerCase()
    // 要摘要时拿到的仍是 PDF（文件本身坏了）：不把二进制当文字显示，留着接口给的摘要。
    if (ct.includes('pdf')) return { mode: 'summary', text: text.value }
    return { mode: want, text: await resp.data.text() }
  }

  function request(id: string, want: 'text' | 'summary', version: string): Promise<TextEntry> {
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

  function display(entry: TextEntry) {
    mode.value = entry.mode
    text.value = entry.text
  }

  function tryCached(id: string, version: string): boolean {
    const hit = cache.get(id)
    if (!hit || hit.version !== version) return false
    remember(id, version, hit.entry)
    display(hit.entry)
    return true
  }

  async function loadText(id: string, want: 'text' | 'summary', version: string) {
    if (tryCached(id, version)) return
    const mine = seq
    loading.value = true
    try {
      const entry = await request(id, want, version)
      if (mine === seq) display(entry)
    } catch (err) {
      if (mine === seq) { mode.value = 'summary'; onError(err) }
    } finally {
      if (mine === seq) loading.value = false
    }
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
    cache.delete(id)
  }

  function abortOther(id: string) {
    if (pending && pending.id !== id) {
      pending.ctrl.abort()
      pending = null
    }
  }

  /** 显示一条记录：先用接口给的模式和摘要；PDF 交给阅读器按 Range 取，文本取回原文（版本一致直接命中缓存）。 */
  async function show(id: string, initialMode: PreviewMode, summary: string, hasBinary: boolean, version = '') {
    syncOwner()
    seq += 1
    abortOther(id)
    shownId = id
    shownVersion = version
    mode.value = initialMode
    text.value = summary
    pdfUrl.value = ''
    loading.value = false
    if (!hasBinary || initialMode === 'summary') return
    if (initialMode === 'pdf') {
      pdfUrl.value = knowledgeContentUrl(id)
      return
    }
    await loadText(id, 'text', version)
  }

  /** 阅读器发现拿到的不是 PDF：改按文本取（服务端回的是摘要 txt）。 */
  async function fallbackToText() {
    if (!shownId) return
    pdfUrl.value = ''
    mode.value = 'summary'
    await loadText(shownId, 'summary', `${shownVersion}:summary`)
  }

  /** 离开页面：中止在途请求；非会话级缓存一并清掉。 */
  function dispose() {
    cancel()
    if (!options.persistent) cache.clear()
  }

  return { loading, mode, text, pdfUrl, show, fallbackToText, cancel, evict, dispose }
}
