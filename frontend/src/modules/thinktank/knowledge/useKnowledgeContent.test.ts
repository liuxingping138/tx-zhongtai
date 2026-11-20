import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearKnowledgeContentCache,
  CONTENT_CACHE_SIZE,
  isOfficeFile,
  useKnowledgeContent,
  type BlobResponse,
} from './useKnowledgeContent'

function pdf(body = '%PDF'): BlobResponse {
  return { data: new Blob([body], { type: 'application/pdf' }), headers: { 'content-type': 'application/pdf' } }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}

describe('useKnowledgeContent', () => {
  let urls = 0
  let create: ReturnType<typeof vi.spyOn>
  const revoked: string[] = []

  beforeEach(() => {
    urls = 0
    revoked.length = 0
    create = vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:${++urls}`)
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(url => { revoked.push(url) })
  })

  afterEach(() => { vi.restoreAllMocks() })

  it('上一条还在转码时切到只有摘要的记录：中止旧请求，不会一直转圈，晚到的 PDF 也不会盖上来', async () => {
    const slow = deferred<BlobResponse>()
    const signals: AbortSignal[] = []
    const content = useKnowledgeContent((_id, signal) => { signals.push(signal!); return slow.promise }, vi.fn())

    const first = content.show('a', 'pdf', '摘要A', true)
    expect(content.loading.value).toBe(true)

    await content.show('b', 'summary', '摘要B', false)
    expect(content.loading.value).toBe(false)
    expect(signals[0]?.aborted).toBe(true)

    slow.resolve(pdf())
    await first
    expect(content.loading.value).toBe(false)
    expect(content.pdfUrl.value).toBe('')
    expect(content.mode.value).toBe('summary')
    expect(content.text.value).toBe('摘要B')
    expect(create).not.toHaveBeenCalled()
  })

  it('同一条记录在路上时再显示一次（重试、路由参数变化）只发一次 /content', async () => {
    const slow = deferred<BlobResponse>()
    const fetchBlob = vi.fn(() => slow.promise)
    const content = useKnowledgeContent(fetchBlob, vi.fn())

    const one = content.show('a', 'pdf', '', true)
    const two = content.show('a', 'pdf', '', true)
    slow.resolve(pdf())
    await Promise.all([one, two])

    expect(fetchBlob).toHaveBeenCalledOnce()
    expect(content.pdfUrl.value).toBe('blob:1')
    expect(content.loading.value).toBe(false)
  })

  it('看过的记录再回来直接用缓存，不再请求；离开页面全部释放', async () => {
    const fetchBlob = vi.fn(() => Promise.resolve(pdf()))
    const content = useKnowledgeContent(fetchBlob, vi.fn())
    await content.show('a', 'pdf', '', true)
    await content.show('b', 'pdf', '', true)
    expect(content.pdfUrl.value).toBe('blob:2')

    content.cancel()
    await content.show('a', 'pdf', '', true)
    expect(fetchBlob).toHaveBeenCalledTimes(2)
    expect(content.pdfUrl.value).toBe('blob:1')
    expect(content.loading.value).toBe(false)
    expect(revoked).toEqual([])

    content.dispose()
    expect(revoked.sort()).toEqual(['blob:1', 'blob:2'])
    expect(content.pdfUrl.value).toBe('')
  })

  it(`最多留 ${CONTENT_CACHE_SIZE} 份，挤出最久没看的并释放它的对象 URL`, async () => {
    const fetchBlob = vi.fn(() => Promise.resolve(pdf()))
    const content = useKnowledgeContent(fetchBlob, vi.fn())
    for (let i = 0; i < CONTENT_CACHE_SIZE; i += 1) await content.show(`r${i}`, 'pdf', '', true)
    await content.show('r0', 'pdf', '', true) // 再看一次 r0，最久没看的变成 r1
    await content.show('new', 'pdf', '', true)

    expect(revoked).toEqual(['blob:2'])
    await content.show('r0', 'pdf', '', true)
    expect(fetchBlob).toHaveBeenCalledTimes(CONTENT_CACHE_SIZE + 1)
    await content.show('r1', 'pdf', '', true)
    expect(fetchBlob).toHaveBeenCalledTimes(CONTENT_CACHE_SIZE + 2)
  })

  it('要 PDF 却拿到文本时回退摘要；文本模式直接显示', async () => {
    const summary: BlobResponse = { data: new Blob(['资料名称：x'], { type: 'text/plain' }) }
    const content = useKnowledgeContent(() => Promise.resolve(summary), vi.fn())
    await content.show('a', 'pdf', '', true)
    expect(content.mode.value).toBe('summary')
    expect(content.text.value).toBe('资料名称：x')

    await content.show('b', 'text', '', true)
    expect(content.mode.value).toBe('text')
    expect(content.text.value).toBe('资料名称：x')
  })

  it('取原文失败回退摘要并提示，不进缓存；被作废的失败不提示', async () => {
    const onError = vi.fn()
    const failing = deferred<BlobResponse>()
    const content = useKnowledgeContent(() => failing.promise.then(() => { throw new Error('503') }), onError)

    const stale = content.show('a', 'pdf', '', true)
    content.cancel()
    failing.resolve(pdf())
    await stale
    expect(onError).not.toHaveBeenCalled()

    const fetchBlob = vi.fn(() => Promise.reject(new Error('503')))
    const now = useKnowledgeContent(fetchBlob, onError)
    await now.show('b', 'pdf', '摘要', true)
    expect(onError).toHaveBeenCalledOnce()
    expect(now.mode.value).toBe('summary')
    expect(now.loading.value).toBe(false)
    await now.show('b', 'pdf', '摘要', true)
    expect(fetchBlob).toHaveBeenCalledTimes(2)
  })

  it('会话级缓存跨页面实例复用，版本变更、换账号或 evict 时自动失效并释放 URL', async () => {
    clearKnowledgeContentCache()
    let owner = 'u1'
    const fetchBlob = vi.fn(() => Promise.resolve(pdf()))

    const firstPage = useKnowledgeContent(fetchBlob, vi.fn(), { persistent: true, getOwner: () => owner })
    await firstPage.show('doc1', 'pdf', '', true, 'v1')
    expect(firstPage.pdfUrl.value).toBe('blob:1')
    firstPage.dispose()
    expect(revoked).toEqual([])

    const secondPage = useKnowledgeContent(fetchBlob, vi.fn(), { persistent: true, getOwner: () => owner })
    await secondPage.show('doc1', 'pdf', '', true, 'v1')
    expect(fetchBlob).toHaveBeenCalledOnce()
    expect(secondPage.pdfUrl.value).toBe('blob:1')

    await secondPage.show('doc1', 'pdf', '', true, 'v2')
    expect(fetchBlob).toHaveBeenCalledTimes(2)
    expect(revoked).toContain('blob:1')
    expect(secondPage.pdfUrl.value).toBe('blob:2')

    owner = 'u2'
    await secondPage.show('doc1', 'pdf', '', true, 'v2')
    expect(fetchBlob).toHaveBeenCalledTimes(3)
    expect(revoked).toContain('blob:2')

    secondPage.evict('doc1')
    expect(revoked).toContain('blob:3')
    clearKnowledgeContentCache()
  })
})

describe('isOfficeFile', () => {
  it('按扩展名或文件格式列识别要转码的 Office 文件', () => {
    expect(isOfficeFile('方案.pptx', '')).toBe(true)
    expect(isOfficeFile('无扩展名', 'WORD')).toBe(true)
    expect(isOfficeFile('白皮书.pdf', 'PDF')).toBe(false)
  })
})
