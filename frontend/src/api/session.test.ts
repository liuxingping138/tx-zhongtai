import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const axiosMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('axios', () => ({ default: axiosMock }))

class FakeChannel {
  static instances: FakeChannel[] = []
  sent: unknown[] = []
  handlers: ((event: { data: unknown }) => void)[] = []
  constructor(public name: string) {
    FakeChannel.instances.push(this)
  }
  postMessage(message: unknown) {
    this.sent.push(message)
  }
  addEventListener(_type: string, handler: (event: { data: unknown }) => void) {
    this.handlers.push(handler)
  }
  receive(data: unknown) {
    this.handlers.forEach(handler => handler({ data }))
  }
}

async function load() {
  vi.resetModules()
  return import('./session')
}

const tokenResponse = (token = 'access-1', expiresIn = 900) => ({
  data: { data: { access_token: token, token_type: 'Bearer', expires_in: expiresIn, must_change_password: false } },
})

beforeEach(() => {
  FakeChannel.instances = []
  axiosMock.get.mockReset()
  axiosMock.post.mockReset()
  vi.stubGlobal('BroadcastChannel', FakeChannel)
  vi.stubGlobal('document', { cookie: '' })
  // 每次取当时的全局定时器，这样测试里切到假定时器后 window.setTimeout 也跟着变。
  vi.stubGlobal('window', {
    setTimeout: (handler: () => void, ms?: number) => globalThis.setTimeout(handler, ms),
    clearTimeout: (id?: number) => globalThis.clearTimeout(id),
  })
  vi.stubGlobal('navigator', {})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('csrf', () => {
  it('从 cookie 里读 csrf_token 并解码，其他 cookie 不受影响', async () => {
    const session = await load()
    vi.stubGlobal('document', { cookie: 'a=1; csrf_token=abc%3D%3D; b=2' })
    expect(session.readCsrfCookie()).toBe('abc==')
    vi.stubGlobal('document', { cookie: 'a=1' })
    expect(session.readCsrfCookie()).toBe('')
  })

  it('cookie 里已有就不再请求接口', async () => {
    const session = await load()
    vi.stubGlobal('document', { cookie: 'csrf_token=from-cookie' })
    expect(await session.ensureCsrfToken()).toBe('from-cookie')
    expect(axiosMock.get).not.toHaveBeenCalled()
    expect(session.getCsrfToken()).toBe('from-cookie')
  })

  it('cookie 没有时向接口要，响应体里的令牌优先', async () => {
    const session = await load()
    axiosMock.get.mockResolvedValue({ data: { data: { csrf_token: 'from-api' } } })
    expect(await session.ensureCsrfToken()).toBe('from-api')
    expect(axiosMock.get).toHaveBeenCalledWith('/api/v1/auth/csrf', { withCredentials: true })
  })
})

describe('访问令牌', () => {
  it('变更通知监听者，清空令牌时停掉续期定时器', async () => {
    vi.useFakeTimers()
    const session = await load()
    const seen: string[] = []
    const off = session.onAccessTokenChange(token => seen.push(token))
    session.setAccessToken('t1')
    session.armAccessRefresh(900)
    session.setAccessToken('')
    off()
    session.setAccessToken('t2')
    expect(seen).toEqual(['t1', ''])
    axiosMock.get.mockResolvedValue({ data: { data: { csrf_token: 'c' } } })
    axiosMock.post.mockResolvedValue(tokenResponse())
    await vi.advanceTimersByTimeAsync(900_000)
    expect(axiosMock.post).not.toHaveBeenCalled()
  })

  it('在到期前两分钟续期，且至少等一分钟', async () => {
    vi.useFakeTimers()
    const session = await load()
    axiosMock.get.mockResolvedValue({ data: { data: { csrf_token: 'c' } } })
    axiosMock.post.mockResolvedValue(tokenResponse('renewed'))
    session.armAccessRefresh(900)
    await vi.advanceTimersByTimeAsync(779_000)
    expect(axiosMock.post).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2_000)
    expect(axiosMock.post).toHaveBeenCalledOnce()
    expect(session.getAccessToken()).toBe('renewed')
  })

  it('无效的有效期不装定时器', async () => {
    vi.useFakeTimers()
    const session = await load()
    session.armAccessRefresh(0)
    session.armAccessRefresh(-5)
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('refreshSession', () => {
  beforeEach(() => {
    axiosMock.get.mockResolvedValue({ data: { data: { csrf_token: 'csrf-1' } } })
  })

  it('同时发起多次只发一个刷新请求', async () => {
    const session = await load()
    axiosMock.post.mockResolvedValue(tokenResponse('shared'))
    const [a, b, c] = await Promise.all([session.refreshSession(), session.refreshSession(), session.refreshSession()])
    expect(axiosMock.post).toHaveBeenCalledOnce()
    expect([a.access_token, b.access_token, c.access_token]).toEqual(['shared', 'shared', 'shared'])
  })

  it('刷新请求带着 csrf 头和凭据，并向其他标签页广播开始与完成', async () => {
    const session = await load()
    axiosMock.post.mockResolvedValue(tokenResponse('tok'))
    await session.refreshSession()
    expect(axiosMock.post.mock.calls[0]?.[2]).toEqual({ withCredentials: true, headers: { 'X-CSRF-Token': 'csrf-1' } })
    const sent = FakeChannel.instances[0]?.sent as { type: string }[]
    expect(sent.map(message => message.type)).toEqual(['refresh-start', 'refresh-done'])
  })

  it('刷新失败时广播失败并把错误抛给调用方，之后可以重试', async () => {
    const session = await load()
    axiosMock.post.mockRejectedValueOnce(new Error('401'))
    await expect(session.refreshSession()).rejects.toThrow('401')
    expect((FakeChannel.instances[0]?.sent as { type: string }[]).at(-1)?.type).toBe('refresh-fail')
    axiosMock.post.mockResolvedValueOnce(tokenResponse('again'))
    expect((await session.refreshSession()).access_token).toBe('again')
  })

  it('响应里没有令牌按失败处理', async () => {
    const session = await load()
    axiosMock.post.mockResolvedValue({ data: { data: null } })
    await expect(session.refreshSession()).rejects.toThrow('没有令牌')
  })

  it('等锁期间别的标签页已经换到新令牌时，直接沿用不再请求', async () => {
    let release!: () => void
    const gate = new Promise<void>(resolve => { release = resolve })
    vi.stubGlobal('navigator', { locks: { request: async (_name: string, run: () => Promise<unknown>) => { await gate; return run() } } })
    const session = await load()
    const pending = session.refreshSession()
    FakeChannel.instances[0]?.receive({ type: 'refresh-done', access_token: 'from-other-tab', must_change_password: false })
    release()
    expect((await pending).access_token).toBe('from-other-tab')
    expect(axiosMock.post).not.toHaveBeenCalled()
  })
})

describe('跨标签页', () => {
  it('其他标签页退出时清掉本地身份并通知监听者，监听可取消', async () => {
    const session = await load()
    session.setAccessToken('t')
    session.setCsrfToken('c')
    const listener = vi.fn()
    const off = session.onRemoteLogout(listener)
    FakeChannel.instances[0]?.receive({ type: 'logout' })
    expect(session.getAccessToken()).toBe('')
    expect(session.getCsrfToken()).toBe('')
    expect(listener).toHaveBeenCalledOnce()
    off()
    FakeChannel.instances[0]?.receive({ type: 'logout' })
    expect(listener).toHaveBeenCalledOnce()
  })

  it('退出时向其他标签页广播', async () => {
    const session = await load()
    session.broadcastLogout()
    expect(FakeChannel.instances[0]?.sent).toEqual([{ type: 'logout' }])
  })
})

describe('isAuthPublicPath', () => {
  it('登录、刷新、csrf 接口出错时不再触发自动续期', async () => {
    const session = await load()
    expect(session.isAuthPublicPath('/auth/login')).toBe(true)
    expect(session.isAuthPublicPath('/api/v1/auth/refresh')).toBe(true)
    expect(session.isAuthPublicPath('/auth/csrf')).toBe(true)
    expect(session.isAuthPublicPath('/system/users')).toBe(false)
    expect(session.isAuthPublicPath(undefined)).toBe(false)
  })
})
