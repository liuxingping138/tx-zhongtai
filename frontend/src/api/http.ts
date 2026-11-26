import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

import { getAccessToken, getCsrfToken, isAuthPublicPath, onAccessTokenChange, onRemoteLogout, refreshRejected, refreshSession, setAccessToken } from './session'
import { ApiRequestError, wasShown } from './errors'
import type { ApiError, ApiResponse } from './types'

interface RetryConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

export interface ApiResponseBody<T> {
  code: string
  message: string
  data: T | null
  request_id: string | null
}

export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  withCredentials: true,
  // 多选筛选按重复参数提交（a=1&a=2），后端 FastAPI 的 list 参数只认这种写法，不认 a[]=1。
  paramsSerializer: { indexes: null },
})

http.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const csrf = getCsrfToken()
  if (csrf) {
    config.headers['X-CSRF-Token'] = csrf
  }
  return config
})

function toApiError(error: AxiosError<ApiResponseBody<unknown>>): ApiRequestError {
  if (error.response) {
    const body = error.response.data
    const retryAfter: unknown = error.response.headers['retry-after']
    return new ApiRequestError({
      status: error.response.status,
      code: body?.code ?? 'UNKNOWN_ERROR',
      message: body?.message ?? '请求失败',
      requestId: body?.request_id ?? null,
      retryAfter: typeof retryAfter === 'string' ? retryAfter : null,
    })
  }
  if (error.code === 'ECONNABORTED') {
    return new ApiRequestError({ status: 0, code: 'TIMEOUT', message: '请求超时，请稍后重试', requestId: null })
  }
  return new ApiRequestError({ status: 0, code: 'NETWORK_ERROR', message: '网络异常，请检查网络连接', requestId: null })
}

/** 503、409 的通用提示只兜底：等页面先处理（页面 catch 都在这一轮微任务里跑完），页面已经用 errorMessage 提示过就不再弹。 */
function notifyUnlessShown(error: ApiError, show: () => void): void {
  setTimeout(() => {
    if (!wasShown(error)) show()
  }, 0)
}

function notifyByStatus(error: ApiError): void {
  if (error.status === 429) {
    ElMessage.warning(error.retryAfter ? `${error.message}（请 ${error.retryAfter} 秒后重试）` : error.message)
    return
  }
  if (error.status === 503) {
    notifyUnlessShown(error, () => ElMessage.error('服务暂时不可用，请稍后重试'))
    return
  }
  if (error.status === 409) {
    notifyUnlessShown(error, () => ElMessage.warning(error.message || '数据已被修改，请刷新后重试'))
  }
}

http.interceptors.response.use(
  (response) => {
    if (response.config.responseType === 'blob') {
      return response as never
    }
    if (response.status === 204 || response.data == null || response.data === '') {
      return null as never
    }
    const body = response.data as ApiResponse<unknown>
    return body.data as never
  },
  async (error: AxiosError<ApiResponseBody<unknown>>) => {
    await parseBlobErrorBody(error)
    const config = error.config as RetryConfig | undefined
    const status = error.response?.status
    if (status === 401 && config && !isAuthPublicPath(config.url)) {
      if (!config._retried) {
        const retried = await retryAfterRefresh(config)
        if (retried) return retried.value
      } else {
        signOutOnce()
      }
    }
    const apiError = toApiError(error)
    if (status === 403) {
      forbiddenHandler?.()
    }
    if (status !== 401) {
      notifyByStatus(apiError)
    }
    return Promise.reject(apiError)
  },
)

/**
 * 401 时续期一次再重发。续期被拒绝就退出登录、照常按 401 失败（返回 null）；
 * 续期连不上就按服务暂时不可用失败，不退出登录。
 */
async function retryAfterRefresh(config: RetryConfig): Promise<{ value: Promise<unknown> } | null> {
  config._retried = true
  try {
    await refreshSession()
    return { value: http(config) }
  } catch (refreshError) {
    const failure = afterRefreshFailure(refreshError)
    if (failure.status === 401) return null
    notifyByStatus(failure)
    return { value: Promise.reject(failure) }
  }
}

/** 下载接口按 blob 收响应，出错时错误体也是 blob，先还原成 JSON 才能取到中文提示。 */
async function parseBlobErrorBody(error: AxiosError<ApiResponseBody<unknown>>): Promise<void> {
  if (!(error.response?.data instanceof Blob)) return
  const text = await error.response.data.text()
  try {
    error.response.data = JSON.parse(text) as ApiResponseBody<unknown>
  } catch {
    error.response.data = { code: 'UNKNOWN_ERROR', message: '请求失败', data: null, request_id: null }
  }
}

/**
 * 续期失败后怎么办：被 IAM 明确拒绝就退出登录（并发的几个请求只退一次）；连不上、5xx 不退出，
 * 当成服务暂时不可用，会话还在，过一会儿再点就好。流式提问（eventStream）也走这里，不各写一套。
 */
export function afterRefreshFailure(error: unknown): ApiRequestError {
  if (refreshRejected(error)) {
    signOutOnce()
    return new ApiRequestError({ status: 401, code: 'AUTH_UNAUTHENTICATED', message: '登录已失效，请重新登录', requestId: null })
  }
  return new ApiRequestError({ status: 503, code: 'DEPENDENCY_UNAVAILABLE', message: '服务暂时不可用，请稍后重试', requestId: null })
}

/** 续期失败时并发的多个请求只触发一次退出登录。 */
function signOutOnce(): void {
  if (signingOut) return
  signingOut = true
  setAccessToken('')
  unauthorizedHandler?.()
}

let unauthorizedHandler: (() => void) | null = null
let forbiddenHandler: (() => void) | null = null
let signingOut = false

onAccessTokenChange((token) => {
  if (token) signingOut = false
})
onRemoteLogout(() => {
  signingOut = true
})

export function notifyUnauthorized(): void {
  signOutOnce()
}

export function notifyForbidden(): void {
  forbiddenHandler?.()
}

export function setUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler
}

export function setForbiddenHandler(handler: () => void): void {
  forbiddenHandler = handler
}

export function request<T>(promise: Promise<unknown>): Promise<T> {
  return promise as Promise<T>
}
