import { ApiRequestError } from './errors'
import { afterRefreshFailure, notifyForbidden, notifyUnauthorized } from './http'
import { getAccessToken, getCsrfToken, refreshSession } from './session'

/**
 * POST 一个 SSE 接口，逐个回调 `data:` 里的 JSON 事件，收到 `[DONE]` 结束。
 *
 * axios 不能边收边读响应体，流式回答只能用 fetch；但要和 http 实例一样带 Authorization / CSRF、
 * 401 时续期重试一次，失败时把后端的中文错误还原成 ApiRequestError。
 */
export async function postEventStream(
  path: string,
  body: unknown,
  onEvent: (event: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response = await send(path, body, signal)
  if (response.status === 401) {
    try {
      await refreshSession()
    } catch (error) {
      // 和普通请求一样：被拒绝就退出登录、提示「登录已失效」，连不上就说服务暂时不可用，不露英文报错。
      throw afterRefreshFailure(error)
    }
    response = await send(path, body, signal)
    if (response.status === 401) {
      notifyUnauthorized()
    }
  }
  if (response.status === 403) {
    notifyForbidden()
  }
  if (!response.ok || !response.body) {
    throw await toError(response)
  }
  let finished: boolean
  try {
    finished = await readEvents(response.body, onEvent)
  } catch (error) {
    throw networkError(error)
  }
  // 连接被干净地断开、没收到 [DONE]：半截回答不能当完整回答给人看。
  if (!finished) throw new ApiRequestError({ status: 0, code: 'STREAM_INTERRUPTED', message: '回答中途断了，请重试', requestId: null })
}

async function send(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'text/event-stream' }
  const token = getAccessToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const csrf = getCsrfToken()
  if (csrf) headers['X-CSRF-Token'] = csrf
  try {
    return await fetch(`/api/v1${path}`, { method: 'POST', headers, body: JSON.stringify(body), credentials: 'include', signal })
  } catch (error) {
    throw networkError(error)
  }
}

/** 断网、连接被重置时 fetch 抛的是「Failed to fetch」「network error」这类英文：换成中文。用户自己停的照原样抛。 */
function networkError(error: unknown): unknown {
  if (error instanceof DOMException && error.name === 'AbortError') return error
  return new ApiRequestError({ status: 0, code: 'NETWORK_ERROR', message: '网络连接中断，请检查网络后重试', requestId: null })
}

async function toError(response: Response): Promise<ApiRequestError> {
  let code = 'UNKNOWN_ERROR'
  let message = response.status === 503 ? '服务暂时不可用，请稍后重试' : '请求失败'
  let requestId: string | null = null
  try {
    const data = (await response.json()) as { code?: string; message?: string; request_id?: string }
    code = data.code ?? code
    message = data.message ?? message
    requestId = data.request_id ?? null
  } catch {
    // 网关直接返回的错误页不是 JSON，沿用按状态码给的提示。
  }
  return new ApiRequestError({ status: response.status, code, message, requestId })
}

/** 按 SSE 规则切分：事件之间空行分隔，只取 data 行。返回是否收到了结束标记 [DONE]。 */
export async function readEvents(stream: ReadableStream<Uint8Array>, onEvent: (event: Record<string, unknown>) => void): Promise<boolean> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      if (dispatch(block, onEvent)) return true
      boundary = buffer.indexOf('\n\n')
    }
    if (done) return dispatch(buffer, onEvent)
  }
}

function dispatch(block: string, onEvent: (event: Record<string, unknown>) => void): boolean {
  for (const line of block.split('\n')) {
    if (!line.startsWith('data:')) continue
    const payload = line.slice(5).trim()
    if (payload === '[DONE]') return true
    try {
      const event: unknown = JSON.parse(payload)
      if (event && typeof event === 'object' && !Array.isArray(event)) onEvent(event as Record<string, unknown>)
    } catch {
      // 半截或非 JSON 的行丢弃，不中断整段回答。
    }
  }
  return false
}
