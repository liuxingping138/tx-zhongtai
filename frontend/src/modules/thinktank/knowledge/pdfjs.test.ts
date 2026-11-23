import { afterEach, describe, expect, it, vi } from 'vitest'

const fail = vi.hoisted(() => ({ next: false }))
const lib = vi.hoisted(() => {
  let src = ''
  const GlobalWorkerOptions = {
    get workerSrc() { return src },
    set workerSrc(value: string) {
      if (fail.next) {
        fail.next = false
        throw new Error('worker setup failed')
      }
      src = value
    },
  }
  return { GlobalWorkerOptions, getDocument: () => null }
})
vi.mock('pdfjs-dist', () => lib)
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '/assets/pdf.worker.min-hash.js' }))

describe('pdfjs', () => {
  afterEach(() => { vi.resetModules() })

  it('按需加载 PDF.js，worker 指向本站打包的文件，只加载一次', async () => {
    const { loadPdfJs } = await import('./pdfjs')
    const first = await loadPdfJs()
    expect(first.GlobalWorkerOptions.workerSrc).toBe('/assets/pdf.worker.min-hash.js')
    expect(await loadPdfJs()).toBe(first)
  })

  it('加载失败时下次重新加载，不一直卡在失败结果上', async () => {
    const { loadPdfJs } = await import('./pdfjs')
    fail.next = true
    await expect(loadPdfJs()).rejects.toThrow('worker setup failed')
    const again = await loadPdfJs()
    expect(again.GlobalWorkerOptions.workerSrc).toBe('/assets/pdf.worker.min-hash.js')
  })

  it('按 Range 只取要画的那几段，令牌放在请求头，CMap、字体、wasm 都从本站取', async () => {
    const { documentOptions, RANGE_CHUNK_SIZE } = await import('./pdfjs')
    const opts = documentOptions('/api/v1/thinktank/knowledge/1/content', 'tok', '/assets/pdfjs-x/')
    expect(opts).toMatchObject({
      url: '/api/v1/thinktank/knowledge/1/content',
      httpHeaders: { Authorization: 'Bearer tok' },
      rangeChunkSize: RANGE_CHUNK_SIZE,
      disableAutoFetch: true,
      disableStream: true,
      cMapUrl: '/assets/pdfjs-x/cmaps/',
      cMapPacked: true,
      standardFontDataUrl: '/assets/pdfjs-x/standard_fonts/',
      wasmUrl: '/assets/pdfjs-x/wasm/',
      iccUrl: '/assets/pdfjs-x/iccs/',
    })
    expect(RANGE_CHUNK_SIZE).toBe(262_144)
    expect(documentOptions('/x', '').httpHeaders).toBeUndefined()
    expect(documentOptions('/x', 't').cMapUrl).toMatch(/^\/assets\/pdfjs-[\d.]+\/cmaps\/$/)
  })

  it('识别 PDF.js 的错误类型', async () => {
    const { isCancelled, isInvalidPdf, responseStatus } = await import('./pdfjs')
    expect(responseStatus({ name: 'ResponseException', status: 401 })).toBe(401)
    expect(responseStatus(new Error('x'))).toBeNull()
    expect(responseStatus(null)).toBeNull()
    expect(isInvalidPdf({ name: 'InvalidPDFException' })).toBe(true)
    expect(isInvalidPdf(undefined)).toBe(false)
    expect(isCancelled({ name: 'AbortException' })).toBe(true)
    expect(isCancelled({ name: 'RenderingCancelledException' })).toBe(true)
    expect(isCancelled(new Error('x'))).toBe(false)
  })
})
