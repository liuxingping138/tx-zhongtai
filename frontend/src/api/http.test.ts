import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const session = vi.hoisted(() => ({
  getAccessToken: vi.fn(() => ''),
  getCsrfToken: vi.fn(() => ''),
  isAuthPublicPath: vi.fn((url?: string) => !!url && url.includes('/auth/')),
  onAccessTokenChange: vi.fn(),
  onRemoteLogout: vi.fn(),
  refreshSession: vi.fn<() => Promise<unknown>>(),
  setAccessToken: vi.fn(),
}))
const message = vi.hoisted(() => ({ warning: vi.fn(), error: vi.fn() }))
vi.mock('./session', () => session)
vi.mock('element-plus', () => ({ ElMessage: message }))

import { http, request, setForbiddenHandler, setUnauthorizedHandler } from './http'

type Responder = (config: InternalAxiosRequestConfig) => { status: number; data?: unknown; headers?: Record<string, string> }

function respondWith(responder: Responder): InternalAxiosRequestConfig[] {
  const calls: InternalAxiosRequestConfig[] = []
  const adapter: AxiosAdapter = (config) => {
    calls.push(config)
    const { status, data, headers = {} } = responder(config)
    const response = { status, data, headers, config, statusText: '' } as AxiosResponse
    if (status >= 400) return Promise.reject(new AxiosError('failed', 'ERR_BAD_REQUEST', config, null, response))
    return Promise.resolve(response)
  }
  http.defaults.adapter = adapter
  return calls
}

const ok = (data: unknown) => ({ status: 200, data: { code: 'OK', message: 'success', data, request_id: 'r1' } })
const fail = (status: number, code: string, text: string, headers: Record<string, string> = {}) => ({
  status, data: { code, message: text, data: null, request_id: 'rid' }, headers,
})

beforeEach(() => {
  session.getAccessToken.mockReset().mockReturnValue('')
  session.getCsrfToken.mockReset().mockReturnValue('')
  session.refreshSession.mockReset()
  session.setAccessToken.mockReset()
  message.warning.mockReset()
  message.error.mockReset()
  setUnauthorizedHandler(() => undefined)
  setForbiddenHandler(() => undefined)
})

describe('请求头', () => {
  it('有令牌就带 Authorization，有 csrf 就带 X-CSRF-Token', async () => {
    session.getAccessToken.mockReturnValue('tok')
    session.getCsrfToken.mockReturnValue('csrf')
    const calls = respondWith(() => ok(null))
    await http.get('/x')
    expect(calls[0]?.headers.Authorization).toBe('Bearer tok')
    expect(calls[0]?.headers['X-CSRF-Token']).toBe('csrf')
  })

  it('没有令牌时不带这两个头', async () => {
    const calls = respondWith(() => ok(null))
    await http.get('/x')
    expect(calls[0]?.headers.Authorization).toBeUndefined()
    expect(calls[0]?.headers['X-CSRF-Token']).toBeUndefined()
  })

  it('多选筛选按重复参数提交，而不是 a[]=1', async () => {
    const calls = respondWith(() => ok(null))
    await http.get('/x', { params: { tag: ['甲', '乙'], page: 1 } })
    const url = http.getUri(calls[0])
    expect(url).toContain('tag=%E7%94%B2&tag=%E4%B9%99')
    expect(url).not.toContain('[]')
  })
})

describe('成功响应', () => {
  it('取信封里的 data', async () => {
    respondWith(() => ok({ id: 7 }))
    expect(await request(http.get('/x'))).toEqual({ id: 7 })
  })

  it('204 和空体返回 null', async () => {
    respondWith(() => ({ status: 204 }))
    expect(await http.get('/x')).toBeNull()
  })
})

describe('错误映射', () => {
  it('业务错误保留状态码、错误码、说明和请求编号', async () => {
    respondWith(() => fail(422, 'VALIDATION_ERROR', '网站名称不能为空'))
    await expect(http.get('/x')).rejects.toMatchObject({
      status: 422, code: 'VALIDATION_ERROR', message: '网站名称不能为空', requestId: 'rid',
    })
  })

  it('限流提示里带上重试秒数', async () => {
    respondWith(() => fail(429, 'RATE_LIMITED', '请求过于频繁', { 'retry-after': '30' }))
    await expect(http.get('/x')).rejects.toMatchObject({ status: 429, retryAfter: '30' })
    expect(message.warning).toHaveBeenCalledWith('请求过于频繁（请 30 秒后重试）')
  })

  it('503 给通用提示，409 用服务端说明，其它状态不弹提示', async () => {
    respondWith(() => fail(503, 'DEPENDENCY_UNAVAILABLE', '内部细节'))
    await expect(http.get('/x')).rejects.toBeTruthy()
    expect(message.error).toHaveBeenCalledWith('服务暂时不可用，请稍后重试')
    respondWith(() => fail(409, 'VERSION_CONFLICT', '数据已被修改'))
    await expect(http.get('/x')).rejects.toBeTruthy()
    expect(message.warning).toHaveBeenCalledWith('数据已被修改')
    message.warning.mockReset()
    message.error.mockReset()
    respondWith(() => fail(422, 'X', '字段错误'))
    await expect(http.get('/x')).rejects.toBeTruthy()
    expect(message.warning).not.toHaveBeenCalled()
    expect(message.error).not.toHaveBeenCalled()
  })

  it('403 触发无权限回调', async () => {
    const forbidden = vi.fn()
    setForbiddenHandler(forbidden)
    respondWith(() => fail(403, 'PERMISSION_DENIED', '没有权限'))
    await expect(http.get('/x')).rejects.toMatchObject({ status: 403 })
    expect(forbidden).toHaveBeenCalledOnce()
  })

  it('没有响应时区分超时和断网', async () => {
    http.defaults.adapter = (config) => Promise.reject(new AxiosError('t', 'ECONNABORTED', config))
    await expect(http.get('/x')).rejects.toMatchObject({ code: 'TIMEOUT', status: 0 })
    http.defaults.adapter = (config) => Promise.reject(new AxiosError('n', 'ERR_NETWORK', config))
    await expect(http.get('/x')).rejects.toMatchObject({ code: 'NETWORK_ERROR', status: 0 })
  })

  it('下载失败时 blob 里的 JSON 错误也能解析成说明', async () => {
    const blob = new Blob([JSON.stringify({ code: 'VALIDATION_ERROR', message: '超过导出上限', data: null, request_id: 'r' })])
    respondWith(() => ({ status: 422, data: blob }))
    await expect(http.get('/x', { responseType: 'blob' })).rejects.toMatchObject({ message: '超过导出上限' })
    respondWith(() => ({ status: 500, data: new Blob(['<html>']) }))
    await expect(http.get('/x', { responseType: 'blob' })).rejects.toMatchObject({ message: '请求失败' })
  })
})

describe('401 自动续期', () => {
  it('续期成功后重放原请求，只重放一次', async () => {
    session.refreshSession.mockResolvedValue({})
    let call = 0
    const calls = respondWith(() => (++call === 1 ? fail(401, 'UNAUTHENTICATED', '未登录') : ok({ id: 1 })))
    expect(await http.get('/users')).toEqual({ id: 1 })
    expect(calls).toHaveLength(2)
    expect(session.refreshSession).toHaveBeenCalledOnce()
  })

  it('重放后仍然 401 不会死循环', async () => {
    session.refreshSession.mockResolvedValue({})
    const calls = respondWith(() => fail(401, 'UNAUTHENTICATED', '未登录'))
    await expect(http.get('/users')).rejects.toMatchObject({ status: 401 })
    expect(calls).toHaveLength(2)
    expect(session.refreshSession).toHaveBeenCalledOnce()
  })

  it('续期失败时清令牌、只回调一次未登录处理，并仍然拒绝', async () => {
    const unauthorized = vi.fn()
    setUnauthorizedHandler(unauthorized)
    session.refreshSession.mockRejectedValue(new Error('expired'))
    respondWith(() => fail(401, 'UNAUTHENTICATED', '未登录'))
    await expect(http.get('/a')).rejects.toMatchObject({ status: 401 })
    await expect(http.get('/b')).rejects.toMatchObject({ status: 401 })
    expect(session.setAccessToken).toHaveBeenCalledWith('')
    expect(unauthorized).toHaveBeenCalledOnce()
    expect(message.warning).not.toHaveBeenCalled()
  })

  it('登录、刷新这类公开接口的 401 不走续期', async () => {
    const calls = respondWith(() => fail(401, 'UNAUTHENTICATED', '用户名或密码错误'))
    await expect(http.post('/auth/login', {})).rejects.toMatchObject({ message: '用户名或密码错误' })
    expect(session.refreshSession).not.toHaveBeenCalled()
    expect(calls).toHaveLength(1)
  })
})
