import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useKnowledgeContent, type BlobResponse } from './useKnowledgeContent'

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

  it('上一条还在转码时切到只有摘要的记录：不会一直转圈，晚到的 PDF 也不会盖上来', async () => {
    const slow = deferred<BlobResponse>()
    const content = useKnowledgeContent(() => slow.promise, vi.fn())

    const first = content.show('a', 'pdf', '摘要A', true)
    expect(content.loading.value).toBe(true)

    await content.show('b', 'summary', '摘要B', false)
    expect(content.loading.value).toBe(false)

    slow.resolve(pdf())
    await first
    expect(content.loading.value).toBe(false)
    expect(content.pdfUrl.value).toBe('')
    expect(content.mode.value).toBe('summary')
    expect(content.text.value).toBe('摘要B')
    expect(create).not.toHaveBeenCalled()
  })

  it('PDF 显示成对象 URL，换记录和离开页面时释放', async () => {
    const content = useKnowledgeContent(() => Promise.resolve(pdf()), vi.fn())
    await content.show('a', 'pdf', '', true)
    expect(content.pdfUrl.value).toBe('blob:1')
    expect(content.loading.value).toBe(false)

    await content.show('b', 'pdf', '', true)
    expect(revoked).toEqual(['blob:1'])
    expect(content.pdfUrl.value).toBe('blob:2')

    content.cancel()
    expect(revoked).toEqual(['blob:1', 'blob:2'])
    expect(content.pdfUrl.value).toBe('')
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

  it('取原文失败回退摘要并提示；被作废的失败不提示', async () => {
    const onError = vi.fn()
    const failing = deferred<BlobResponse>()
    const content = useKnowledgeContent(() => failing.promise.then(() => { throw new Error('503') }), onError)

    const stale = content.show('a', 'pdf', '', true)
    content.cancel()
    failing.resolve(pdf())
    await stale
    expect(onError).not.toHaveBeenCalled()

    const now = useKnowledgeContent(() => Promise.reject(new Error('503')), onError)
    await now.show('b', 'pdf', '摘要', true)
    expect(onError).toHaveBeenCalledOnce()
    expect(now.mode.value).toBe('summary')
    expect(now.loading.value).toBe(false)
  })
})
