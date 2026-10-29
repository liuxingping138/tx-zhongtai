import { afterEach, describe, expect, it, vi } from 'vitest'

const session = vi.hoisted(() => ({ token: 'old', refreshes: 0 }))
vi.mock('./session', () => ({
  getAccessToken: () => session.token,
  getCsrfToken: () => 'csrf-1',
  refreshSession: () => {
    session.refreshes += 1
    session.token = 'new'
    return Promise.resolve({})
  },
}))
vi.mock('./http', () => ({
  afterRefreshFailure: () => ({ status: 401, code: 'AUTH_UNAUTHENTICATED', message: '登录已失效，请重新登录' }),
}))

import { postEventStream, readEvents } from './eventStream'

function body(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  session.token = 'old'
  session.refreshes = 0
})

describe('SSE 解析', () => {
  it('跨块拼接事件，跳过坏行，遇到 [DONE] 停止', async () => {
    const events: unknown[] = []
    await readEvents(body(['data: {"text":"你', '"}\n\ndata: 坏\n\n', 'event: x\ndata: {"text":"好"}\n\n', 'data: [DONE]\n\ndata: {"text":"多余"}\n\n']), e => events.push(e))
    expect(events).toEqual([{ text: '你' }, { text: '好' }])
  })

  it('没有 [DONE] 时也处理最后一块，并说明没收到结束标记', async () => {
    const events: unknown[] = []
    expect(await readEvents(body(['data: {"a":1}']), e => events.push(e))).toBe(false)
    expect(events).toEqual([{ a: 1 }])
    expect(await readEvents(body(['data: {"a":1}\n\ndata: [DONE]\n\n']), () => undefined)).toBe(true)
  })
})

describe('postEventStream', () => {
  it('带上令牌和 CSRF，401 时续期后重试一次', async () => {
    const calls: { auth: string; csrf: string }[] = []
    vi.stubGlobal('fetch', vi.fn((_: string, init: RequestInit) => {
      const headers = init.headers as Record<string, string>
      calls.push({ auth: headers.Authorization ?? '', csrf: headers['X-CSRF-Token'] ?? '' })
      if (calls.length === 1) return Promise.resolve(new Response('', { status: 401 }))
      return Promise.resolve(new Response(body(['data: {"text":"ok"}\n\n', 'data: [DONE]\n\n'])))
    }))
    const events: unknown[] = []
    await postEventStream('/ai/stream/chat', { message: 'hi' }, e => events.push(e))
    expect(calls).toEqual([{ auth: 'Bearer old', csrf: 'csrf-1' }, { auth: 'Bearer new', csrf: 'csrf-1' }])
    expect(session.refreshes).toBe(1)
    expect(events).toEqual([{ text: 'ok' }])
  })

  it('把后端的中文错误还原成 ApiRequestError，非 JSON 时按状态码给提示', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ code: 'VALIDATION_ERROR', message: '未知模型：x' }), { status: 422 }))))
    await expect(postEventStream('/ai/stream/chat', {}, () => undefined)).rejects.toMatchObject({ status: 422, message: '未知模型：x' })
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('<html>', { status: 503 }))))
    await expect(postEventStream('/ai/stream/chat', {}, () => undefined)).rejects.toMatchObject({ status: 503, message: '服务暂时不可用，请稍后重试' })
  })

  it('半截回答不当完整回答，断网不露英文报错', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(body(['data: {"text":"一半"}\n\n'])))))
    await expect(postEventStream('/ai/stream/chat', {}, () => undefined)).rejects.toMatchObject({ message: '回答中途断了，请重试' })
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    await expect(postEventStream('/ai/stream/chat', {}, () => undefined)).rejects.toMatchObject({ message: '网络连接中断，请检查网络后重试' })
  })
})
