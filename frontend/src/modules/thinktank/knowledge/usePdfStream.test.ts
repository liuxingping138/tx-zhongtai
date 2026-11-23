import type { DocumentInitParameters } from 'pdfjs-dist/types/src/display/api'
import { describe, expect, it, vi } from 'vitest'

import { usePdfStream, type PdfStreamDeps } from './usePdfStream'

interface FakeTask {
  promise: Promise<unknown>
  destroy: ReturnType<typeof vi.fn>
}

function fakeDoc(numPages = 3, width = 600, height = 800) {
  return {
    numPages,
    getPage: vi.fn(() => Promise.resolve({ getViewport: ({ scale }: { scale: number }) => ({ width: width * scale, height: height * scale }) })),
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (err: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

/** PDF.js 抛出的错误：带 name，取数被拒时带 HTTP 状态码。 */
function pdfError(name: string, status?: number): Error {
  return Object.assign(new Error(name), { name, status })
}

function task(result: unknown, ok = true): FakeTask {
  const promise = ok ? Promise.resolve(result) : Promise.reject(result instanceof Error ? result : new Error(String(result)))
  promise.catch(() => undefined)
  return { promise, destroy: vi.fn(() => Promise.resolve()) }
}

function setup(tasks: FakeTask[], overrides: Partial<PdfStreamDeps> = {}) {
  let token = 't1'
  const calls: DocumentInitParameters[] = []
  const getDocument = vi.fn((opts: DocumentInitParameters) => {
    calls.push(opts)
    const next = tasks.shift()
    if (!next) throw new Error('no more tasks')
    return next
  })
  const deps: PdfStreamDeps = {
    load: () => Promise.resolve({ getDocument } as unknown as Awaited<ReturnType<PdfStreamDeps['load']>>),
    getToken: () => token,
    refresh: vi.fn(() => { token = 't2'; return Promise.resolve() }),
    ...overrides,
  }
  return { stream: usePdfStream(deps), deps, calls, getDocument }
}

const unauthorized = pdfError('ResponseException', 401)

describe('usePdfStream', () => {
  it('打开后量出第一页尺寸、页数，带上当前令牌', async () => {
    const { stream, calls } = setup([task(fakeDoc(55, 595, 842))])
    const opening = stream.open('/content')
    expect(stream.status.value).toBe('loading')
    await opening
    expect(stream.status.value).toBe('ready')
    expect(stream.numPages.value).toBe(55)
    expect(stream.baseSize.value).toEqual({ width: 595, height: 842 })
    expect(stream.generation.value).toBe(1)
    expect(calls[0]?.httpHeaders).toEqual({ Authorization: 'Bearer t1' })
    expect(calls[0]?.disableStream).toBe(true)
    await expect(stream.getPage(2)).resolves.toBeDefined()
  })

  it('打开时 401：续期一次、用新令牌重开', async () => {
    const { stream, calls, deps } = setup([task(unauthorized, false), task(fakeDoc())])
    await stream.open('/content')
    expect(deps.refresh).toHaveBeenCalledOnce()
    expect(calls.map(c => c.httpHeaders)).toEqual([{ Authorization: 'Bearer t1' }, { Authorization: 'Bearer t2' }])
    expect(stream.status.value).toBe('ready')
  })

  it('续期后仍 401、或续期被拒：报错不再重试', async () => {
    const twice = setup([task(unauthorized, false), task(unauthorized, false)])
    await twice.stream.open('/content')
    expect(twice.deps.refresh).toHaveBeenCalledOnce()
    expect(twice.stream.status.value).toBe('error')
    expect(twice.stream.errorText.value).toBe('登录已失效，请重新登录后再看')

    const rejected = setup([task(unauthorized, false)], {
      refresh: () => Promise.reject(Object.assign(new Error('x'), { status: 401 })),
    })
    await rejected.stream.open('/content')
    expect(rejected.stream.status.value).toBe('error')
  })

  it.each([
    [pdfError('ResponseException', 403), '没有权限查看这份原文'],
    [pdfError('ResponseException', 404), '原文不存在或已被删除'],
    [pdfError('ResponseException', 503), '文件服务暂时不可用，请稍后重试'],
    [new Error('network'), '原文加载失败，请重试'],
  ])('打开失败给出能看懂的提示 %#', async (err, text) => {
    const { stream } = setup([task(err, false)])
    await stream.open('/content')
    expect(stream.status.value).toBe('error')
    expect(stream.errorText.value).toBe(text)
  })

  it('拿到的不是 PDF（服务端回了摘要文本）：标成 invalid 交给上层改用文本', async () => {
    const { stream } = setup([task(pdfError('InvalidPDFException'), false)])
    await stream.open('/content')
    expect(stream.status.value).toBe('invalid')
  })

  it('换记录时销毁上一份：中止它的 Range 请求，晚到的结果不会盖上来', async () => {
    const slow = deferred<unknown>()
    const first: FakeTask = { promise: slow.promise, destroy: vi.fn(() => { slow.reject(pdfError('AbortException')); return Promise.resolve() }) }
    const second = task(fakeDoc(7))
    const { stream, getDocument } = setup([first, second])
    const a = stream.open('/a')
    await vi.waitFor(() => expect(getDocument).toHaveBeenCalledOnce())
    const b = stream.open('/b')
    await Promise.all([a, b])
    expect(first.destroy).toHaveBeenCalledOnce()
    expect(stream.status.value).toBe('ready')
    expect(stream.numPages.value).toBe(7)
  })

  it('关闭（离开页面）立即销毁文档；打开空地址等于关闭', async () => {
    const t = task(fakeDoc())
    const { stream } = setup([t])
    await stream.open('/content')
    await stream.close()
    expect(t.destroy).toHaveBeenCalledOnce()
    expect(stream.status.value).toBe('idle')
    expect(stream.getPage(1)).toBeNull()
    expect(stream.numPages.value).toBe(0)

    await stream.open('')
    expect(stream.status.value).toBe('idle')
  })

  it('看的过程中某页取数 401：续期后重开（并发的几页只续期一次）；其他错误留给那一页', async () => {
    const { stream, deps, getDocument } = setup([task(fakeDoc()), task(fakeDoc())])
    await stream.open('/content')
    expect(await stream.onPageError(new Error('render'))).toBe(false)

    const results = await Promise.all([stream.onPageError(unauthorized), stream.onPageError(unauthorized)])
    expect(results).toEqual([true, true])
    expect(deps.refresh).toHaveBeenCalledOnce()
    expect(getDocument).toHaveBeenCalledTimes(2)
    expect(stream.status.value).toBe('ready')
    expect(stream.generation.value).toBe(2)
  })

  it('页内 401 续期被拒时报错；关闭后不再续期', async () => {
    const { stream } = setup([task(fakeDoc())], { refresh: () => Promise.reject(Object.assign(new Error('x'), { status: 401 })) })
    await stream.open('/content')
    await stream.onPageError(unauthorized)
    expect(stream.status.value).toBe('error')

    await stream.close()
    expect(await stream.onPageError(unauthorized)).toBe(false)
  })

  it('重试按原地址重新打开', async () => {
    const { stream, getDocument } = setup([task(new Error('x'), false), task(fakeDoc())])
    await stream.open('/content')
    expect(stream.status.value).toBe('error')
    await stream.retry()
    expect(stream.status.value).toBe('ready')
    expect(getDocument).toHaveBeenCalledTimes(2)
  })

  it('查找时才按页取文字块，跳过标记内容；没有文档时返回 null', async () => {
    const doc = fakeDoc(2)
    const getTextContent = vi.fn(() => Promise.resolve({ items: [{ str: '数字' }, { type: 'beginMarkedContent' }, { str: '政府' }] }))
    doc.getPage.mockImplementation(() => Promise.resolve({
      getViewport: ({ scale }: { scale: number }) => ({ width: 600 * scale, height: 800 * scale }),
      getTextContent,
    }))
    const { stream } = setup([task(doc)])
    expect(await stream.getPageText(1)).toBeNull()
    await stream.open('/content')
    expect(getTextContent).not.toHaveBeenCalled()
    expect(await stream.getPageText(2)).toEqual(['数字', '政府'])
    expect(doc.getPage).toHaveBeenLastCalledWith(2)
  })
})
