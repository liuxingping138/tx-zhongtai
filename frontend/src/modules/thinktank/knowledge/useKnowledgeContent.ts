import { ref } from 'vue'

export type PreviewMode = 'pdf' | 'text' | 'summary'

export interface BlobResponse {
  data: Blob
  headers?: Record<string, unknown>
}

/**
 * 预览页右栏的原文：PDF 用对象 URL 内嵌，文本直接显示，取不到回退摘要。
 *
 * 每次加载、切换记录、离开页面都把序号加一：晚到的旧请求（Office 转码可能要一分钟）只会被丢掉，
 * 不会盖掉新记录的内容，也不会留下一直转圈的加载态；换掉或离开时释放上一份 PDF 的对象 URL。
 */
export function useKnowledgeContent(
  fetchBlob: (id: string) => Promise<BlobResponse>,
  onError: (err: unknown) => void,
) {
  const loading = ref(false)
  const mode = ref<PreviewMode>('summary')
  const text = ref('')
  const pdfUrl = ref('')
  let seq = 0

  function revoke() {
    if (pdfUrl.value) { URL.revokeObjectURL(pdfUrl.value); pdfUrl.value = '' }
  }

  /** 作废还在路上的请求、释放上一份 PDF；换记录前和离开页面时调。 */
  function cancel() {
    seq += 1
    revoke()
    loading.value = false
  }

  async function apply(want: 'pdf' | 'text', resp: BlobResponse, mine: number) {
    const ct = String((resp.headers?.['content-type'] as string | undefined) || resp.data.type || '').toLowerCase()
    if (want === 'pdf' && ct.includes('pdf')) {
      pdfUrl.value = URL.createObjectURL(resp.data)
      return
    }
    // 要 PDF 却拿到文本：服务端转不出来回的是摘要
    const body = await resp.data.text()
    if (mine !== seq) return
    mode.value = want === 'pdf' ? 'summary' : want
    text.value = body
  }

  /** 显示一条记录：先用接口给的模式和摘要，有源文件再取原文。 */
  async function show(id: string, initialMode: PreviewMode, summary: string, hasBinary: boolean) {
    cancel()
    const mine = seq
    mode.value = initialMode
    text.value = summary
    if (!hasBinary || initialMode === 'summary') return
    loading.value = true
    try {
      const resp = await fetchBlob(id)
      if (mine === seq) await apply(initialMode, resp, mine)
    } catch (err) {
      if (mine === seq) { mode.value = 'summary'; onError(err) }
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  return { loading, mode, text, pdfUrl, show, cancel }
}
