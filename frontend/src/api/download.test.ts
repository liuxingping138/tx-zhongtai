import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('./http', () => ({ http: httpMock }))

import { downloadBlob, downloadFile } from './download'

beforeEach(() => {
  vi.useFakeTimers()
  httpMock.get.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function stubBrowser() {
  const link = { href: '', download: '', hidden: false, click: vi.fn(), remove: vi.fn() }
  const body = { appendChild: vi.fn() }
  const revoke = vi.fn()
  vi.stubGlobal('document', { createElement: () => link, body })
  vi.stubGlobal('URL', { createObjectURL: () => 'blob:abc', revokeObjectURL: revoke })
  vi.stubGlobal('window', { setTimeout: (handler: () => void, ms?: number) => globalThis.setTimeout(handler, ms) })
  return { link, body, revoke }
}

describe('downloadBlob', () => {
  it('链接先挂到页面再点击，对象地址延后释放，立即释放部分浏览器会拿不到数据', () => {
    const { link, body, revoke } = stubBrowser()
    downloadBlob(new Blob(['x']), '导出.xlsx')
    expect(body.appendChild).toHaveBeenCalledWith(link)
    expect(link.download).toBe('导出.xlsx')
    expect(link.click).toHaveBeenCalledOnce()
    expect(link.remove).toHaveBeenCalledOnce()
    expect(revoke).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1000)
    expect(revoke).toHaveBeenCalledWith('blob:abc')
  })
})

describe('downloadFile', () => {
  it('走统一的 http 实例，空筛选项不会发给后端', async () => {
    const { link } = stubBrowser()
    httpMock.get.mockResolvedValue({ data: new Blob(['x']) })
    await downloadFile('/policy/sources/export', '信源.xlsx', { site_name: ['甲'], tag: [], city: '', page: undefined, n: 0 })
    const [path, options] = httpMock.get.mock.calls[0] as [string, { params: object; responseType: string; timeout: number }]
    expect(path).toBe('/policy/sources/export')
    expect(options.params).toEqual({ site_name: ['甲'], n: 0 })
    expect(options.responseType).toBe('blob')
    expect(options.timeout).toBe(600_000)
    expect(link.download).toBe('信源.xlsx')
  })

  it('没有筛选条件时不传 params', async () => {
    stubBrowser()
    httpMock.get.mockResolvedValue({ data: new Blob(['x']) })
    await downloadFile('/x', 'a.xlsx')
    expect((httpMock.get.mock.calls[0] as [string, { params: unknown }])[1].params).toBeUndefined()
  })

  it('请求失败时不触发下载并把错误交给调用方', async () => {
    const { link } = stubBrowser()
    httpMock.get.mockRejectedValue({ status: 422, message: '超过导出上限' })
    await expect(downloadFile('/x', 'a.xlsx')).rejects.toMatchObject({ message: '超过导出上限' })
    expect(link.click).not.toHaveBeenCalled()
  })
})
