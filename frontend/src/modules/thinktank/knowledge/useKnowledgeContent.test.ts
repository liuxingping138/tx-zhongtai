import { describe, expect, it, vi } from 'vitest'

import { setAccessToken } from '@/api/session'
import {
  clearKnowledgeContentCache,
  CONTENT_CACHE_SIZE,
  isOfficeFile,
  knowledgeContentUrl,
  thinktankContentUrl,
  useKnowledgeContent,
  type BlobResponse,
} from './useKnowledgeContent'

function textResp(body = '正文'): BlobResponse {
  return { data: new Blob([body], { type: 'text/plain' }), headers: { 'content-type': 'text/plain; charset=utf-8' } }
}

function pdfResp(): BlobResponse {
  return { data: new Blob(['%PDF'], { type: 'application/pdf' }), headers: { 'content-type': 'application/pdf' } }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}

describe('useKnowledgeContent', () => {
  it('PDF 不整份下载：只给出 /content 地址交给 PDF.js 按 Range 取', async () => {
    const fetchBlob = vi.fn(() => Promise.resolve(pdfResp()))
    const content = useKnowledgeContent(fetchBlob, vi.fn())
    await content.show('a/b', 'pdf', '摘要', true, 'v1')
    expect(fetchBlob).not.toHaveBeenCalled()
    expect(content.mode.value).toBe('pdf')
    expect(content.loading.value).toBe(false)
    expect(content.pdfUrl.value).toBe('/api/v1/thinktank/knowledge/a%2Fb/content')
    expect(knowledgeContentUrl('x')).toBe('/api/v1/thinktank/knowledge/x/content')

    content.cancel()
    expect(content.pdfUrl.value).toBe('')
  })

  it('没有源文件或只有摘要时不取原文', async () => {
    const fetchBlob = vi.fn(() => Promise.resolve(textResp()))
    const content = useKnowledgeContent(fetchBlob, vi.fn())
    await content.show('a', 'pdf', '摘要A', false)
    await content.show('b', 'summary', '摘要B', true)
    expect(fetchBlob).not.toHaveBeenCalled()
    expect(content.mode.value).toBe('summary')
    expect(content.text.value).toBe('摘要B')
    expect(content.pdfUrl.value).toBe('')
  })

  it('上一条文本还在路上时切到别的记录：中止旧请求，晚到的结果不会盖上来', async () => {
    const slow = deferred<BlobResponse>()
    const signals: AbortSignal[] = []
    const content = useKnowledgeContent((_id, signal) => { signals.push(signal!); return slow.promise }, vi.fn())

    const first = content.show('a', 'text', '摘要A', true)
    expect(content.loading.value).toBe(true)

    await content.show('b', 'pdf', '摘要B', true)
    expect(content.loading.value).toBe(false)
    expect(signals[0]?.aborted).toBe(true)

    slow.resolve(textResp('A 的正文'))
    await first
    expect(content.mode.value).toBe('pdf')
    expect(content.text.value).toBe('摘要B')
  })

  it('同一条记录在路上时再显示一次只发一次 /content', async () => {
    const slow = deferred<BlobResponse>()
    const fetchBlob = vi.fn(() => slow.promise)
    const content = useKnowledgeContent(fetchBlob, vi.fn())

    const one = content.show('a', 'text', '', true)
    const two = content.show('a', 'text', '', true)
    slow.resolve(textResp('正文'))
    await Promise.all([one, two])

    expect(fetchBlob).toHaveBeenCalledOnce()
    expect(content.text.value).toBe('正文')
    expect(content.mode.value).toBe('text')
  })

  it(`文本看过再回来直接用缓存；最多留 ${CONTENT_CACHE_SIZE} 份，挤出最久没看的`, async () => {
    const fetchBlob = vi.fn((id: string) => Promise.resolve(textResp(`正文-${id}`)))
    const content = useKnowledgeContent(fetchBlob, vi.fn())
    for (let i = 0; i < CONTENT_CACHE_SIZE; i += 1) await content.show(`r${i}`, 'text', '', true)
    await content.show('r0', 'text', '', true) // 再看一次 r0，最久没看的变成 r1
    expect(fetchBlob).toHaveBeenCalledTimes(CONTENT_CACHE_SIZE)
    expect(content.text.value).toBe('正文-r0')

    await content.show('new', 'text', '', true)
    await content.show('r0', 'text', '', true)
    expect(fetchBlob).toHaveBeenCalledTimes(CONTENT_CACHE_SIZE + 1)
    await content.show('r1', 'text', '', true)
    expect(fetchBlob).toHaveBeenCalledTimes(CONTENT_CACHE_SIZE + 2)

    content.dispose()
    await content.show('r0', 'text', '', true)
    expect(fetchBlob).toHaveBeenCalledTimes(CONTENT_CACHE_SIZE + 3)
  })

  it('阅读器发现不是 PDF（服务端回了摘要 txt）时改按文本显示；真是坏 PDF 时保留接口摘要', async () => {
    const fetchBlob = vi.fn(() => Promise.resolve(textResp('资料名称：x')))
    const content = useKnowledgeContent(fetchBlob, vi.fn())
    await content.fallbackToText() // 还没显示任何记录：什么都不做
    expect(fetchBlob).not.toHaveBeenCalled()

    await content.show('a', 'pdf', '接口摘要', true, 'v1')
    await content.fallbackToText()
    expect(content.pdfUrl.value).toBe('')
    expect(content.mode.value).toBe('summary')
    expect(content.text.value).toBe('资料名称：x')

    const broken = useKnowledgeContent(() => Promise.resolve(pdfResp()), vi.fn())
    await broken.show('b', 'pdf', '接口摘要', true)
    await broken.fallbackToText()
    expect(broken.mode.value).toBe('summary')
    expect(broken.text.value).toBe('接口摘要')
  })

  it('取原文失败回退摘要并提示，不进缓存；被作废的失败不提示', async () => {
    const onError = vi.fn()
    const failing = deferred<BlobResponse>()
    const content = useKnowledgeContent(() => failing.promise.then(() => { throw new Error('503') }), onError)

    const stale = content.show('a', 'text', '', true)
    content.cancel()
    failing.resolve(textResp())
    await stale
    expect(onError).not.toHaveBeenCalled()

    const fetchBlob = vi.fn(() => Promise.reject(new Error('503')))
    const now = useKnowledgeContent(fetchBlob, onError)
    await now.show('b', 'text', '摘要', true)
    expect(onError).toHaveBeenCalledOnce()
    expect(now.mode.value).toBe('summary')
    expect(now.loading.value).toBe(false)
    await now.show('b', 'text', '摘要', true)
    expect(fetchBlob).toHaveBeenCalledTimes(2)
  })

  it('会话级缓存跨页面实例复用，版本变更、换账号或 evict 时失效', async () => {
    clearKnowledgeContentCache()
    let owner = 'u1'
    const fetchBlob = vi.fn(() => Promise.resolve(textResp('正文')))

    const firstPage = useKnowledgeContent(fetchBlob, vi.fn(), { persistent: true, getOwner: () => owner })
    await firstPage.show('doc1', 'text', '', true, 'v1')
    firstPage.dispose()

    const secondPage = useKnowledgeContent(fetchBlob, vi.fn(), { persistent: true, getOwner: () => owner })
    await secondPage.show('doc1', 'text', '', true, 'v1')
    expect(fetchBlob).toHaveBeenCalledOnce()
    expect(secondPage.text.value).toBe('正文')

    await secondPage.show('doc1', 'text', '', true, 'v2')
    expect(fetchBlob).toHaveBeenCalledTimes(2)

    owner = 'u2'
    await secondPage.show('doc1', 'text', '', true, 'v2')
    expect(fetchBlob).toHaveBeenCalledTimes(3)

    secondPage.evict('doc1')
    await secondPage.show('doc1', 'text', '', true, 'v2')
    expect(fetchBlob).toHaveBeenCalledTimes(4)

    owner = ''
    await secondPage.show('doc1', 'text', '', true, 'v2')
    expect(fetchBlob).toHaveBeenCalledTimes(5) // 没登录身份时不复用任何缓存
    clearKnowledgeContentCache()
  })

  it('登录令牌清空（退出/远端登出）时自动清空会话级缓存，非空令牌刷新不清缓存', async () => {
    clearKnowledgeContentCache()
    setAccessToken('tok-1')
    const fetchBlob = vi.fn(() => Promise.resolve(textResp('正文')))
    const page = useKnowledgeContent(fetchBlob, vi.fn(), { persistent: true, getOwner: () => 'u1' })
    await page.show('doc1', 'text', '', true, 'v1')
    expect(fetchBlob).toHaveBeenCalledTimes(1)

    setAccessToken('tok-2')
    await page.show('doc1', 'text', '', true, 'v1')
    expect(fetchBlob).toHaveBeenCalledTimes(1)

    setAccessToken('')
    await page.show('doc1', 'text', '', true, 'v1')
    expect(fetchBlob).toHaveBeenCalledTimes(2)
    clearKnowledgeContentCache()
  })

  it('支持按子库前缀生成 /content 地址并按子库隔离会话缓存', async () => {
    clearKnowledgeContentCache()
    expect(thinktankContentUrl('reports', 'r/1')).toBe('/api/v1/thinktank/reports/r%2F1/content')
    expect(thinktankContentUrl('proposals', 'p1')).toBe('/api/v1/thinktank/proposals/p1/content')

    const fetchReport = vi.fn(() => Promise.resolve(textResp('报告正文')))
    const fetchProposal = vi.fn(() => Promise.resolve(textResp('方案正文')))
    const reportContent = useKnowledgeContent(fetchReport, vi.fn(), { persistent: true, getOwner: () => 'u1', library: 'reports' })
    const proposalContent = useKnowledgeContent(fetchProposal, vi.fn(), { persistent: true, getOwner: () => 'u1', library: 'proposals' })

    await reportContent.show('same-id', 'pdf', '', true, 'v1')
    expect(reportContent.pdfUrl.value).toBe('/api/v1/thinktank/reports/same-id/content')

    await reportContent.show('same-id', 'text', '', true, 'v1')
    await proposalContent.show('same-id', 'text', '', true, 'v1')
    expect(reportContent.text.value).toBe('报告正文')
    expect(proposalContent.text.value).toBe('方案正文')
    expect(fetchReport).toHaveBeenCalledOnce()
    expect(fetchProposal).toHaveBeenCalledOnce()
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
