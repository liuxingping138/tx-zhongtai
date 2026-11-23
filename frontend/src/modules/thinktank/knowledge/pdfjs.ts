import type { DocumentInitParameters } from 'pdfjs-dist/types/src/display/api'

/** PDF.js 只在预览页用：按需加载，worker 由 Vite 打进本站静态资源，不走外网 CDN。 */
export type PdfJsLib = typeof import('pdfjs-dist')

/** 每段 Range 取 256KB：第一页（线性化后在文件开头）通常一两段就够，段太小请求数和鉴权次数都多。 */
export const RANGE_CHUNK_SIZE = 262_144

let loader: Promise<PdfJsLib> | null = null

export function loadPdfJs(): Promise<PdfJsLib> {
  loader ??= Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')])
    .then(([lib, worker]) => {
      lib.GlobalWorkerOptions.workerSrc = worker.default
      return lib
    })
    .catch((err: unknown) => {
      loader = null // 网络抖动没加载到脚本：下次重试时重新加载
      throw err
    })
  return loader
}

/**
 * 打开一份按 Range 分段读的 PDF。
 *
 * - `disableStream` + `disableAutoFetch`：只取当前要画的页用到的那几段，不在后台把整份拉完
 *   （PDF.js 文档：不关 stream 的话 disableAutoFetch 不起作用，整份仍会顺着第一个请求下完，和 Range 抢带宽）。
 * - 令牌放在请求头里；PDF.js 打开文档时就把请求头定下来了，过期后要续期并重新打开（见 usePdfStream）。
 * - CMap、标准字体、wasm、ICC 都从本站取：内网、CSP 只放行 'self' 也能正确显示中文。
 */
export function documentOptions(url: string, token: string, assetBase = __PDFJS_ASSET_BASE__): DocumentInitParameters {
  return {
    url,
    httpHeaders: token ? { Authorization: `Bearer ${token}` } : undefined,
    withCredentials: false,
    rangeChunkSize: RANGE_CHUNK_SIZE,
    disableAutoFetch: true,
    disableStream: true,
    cMapUrl: `${assetBase}cmaps/`,
    cMapPacked: true,
    standardFontDataUrl: `${assetBase}standard_fonts/`,
    wasmUrl: `${assetBase}wasm/`,
    iccUrl: `${assetBase}iccs/`,
  }
}

/** PDF.js 的取数请求被拒（ResponseException）时带 HTTP 状态码。 */
export function responseStatus(err: unknown): number | null {
  const status = (err as { status?: unknown } | null)?.status
  return typeof status === 'number' ? status : null
}

/** 拿到的不是 PDF：服务端回了文本摘要（转码失败、源文件不存在），或文件本身坏了。 */
export function isInvalidPdf(err: unknown): boolean {
  return (err as { name?: unknown } | null)?.name === 'InvalidPDFException'
}

/** 主动销毁（换记录、离开页面）时 PDF.js 抛出的取消，不是错误。 */
export function isCancelled(err: unknown): boolean {
  const name = (err as { name?: unknown } | null)?.name
  return name === 'AbortException' || name === 'RenderingCancelledException'
}
