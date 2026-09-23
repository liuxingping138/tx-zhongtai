import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

import { getAccessToken, getCsrfToken, isAuthPublicPath, refreshSession, setAccessToken } from './session'
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

function toApiError(error: AxiosError<ApiResponseBody<unknown>>): ApiError {
  if (error.response) {
    const body = error.response.data
    return {
      status: error.response.status,
      code: body?.code ?? 'UNKNOWN_ERROR',
      message: body?.message ?? '请求失败',
      requestId: body?.request_id ?? null,
      retryAfter: error.response.headers['retry-after'] ?? null,
    }
  }
  return { status: 0, code: 'NETWORK_ERROR', message: '网络异常，请检查网络连接', requestId: null }
}

function notifyByStatus(error: ApiError): void {
  if (error.status === 429) {
    ElMessage.warning(error.retryAfter ? `${error.message}（请 ${error.retryAfter} 秒后重试）` : error.message)
    return
  }
  if (error.status === 503) {
    ElMessage.error('服务暂时不可用，请稍后重试')
    return
  }
  if (error.status === 409) {
    ElMessage.warning(error.message || '数据已被修改，请刷新后重试')
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
    if (error.response?.data instanceof Blob) {
      const text = await error.response.data.text()
      try {
        error.response.data = JSON.parse(text) as ApiResponseBody<unknown>
      } catch {
        error.response.data = {
          code: 'UNKNOWN_ERROR',
          message: '请求失败',
          data: null,
          request_id: null,
        }
      }
    }
    const config = error.config as RetryConfig | undefined
    const status = error.response?.status
    if (
      status === 401 &&
      config &&
      !config._retried &&
      !isAuthPublicPath(config.url)
    ) {
      config._retried = true
      try {
        await refreshSession()
        return http(config)
      } catch {
        setAccessToken('')
        unauthorizedHandler?.()
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

let unauthorizedHandler: (() => void) | null = null
let forbiddenHandler: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler
}

export function setForbiddenHandler(handler: () => void): void {
  forbiddenHandler = handler
}

export function request<T>(promise: Promise<unknown>): Promise<T> {
  return promise as Promise<T>
}
