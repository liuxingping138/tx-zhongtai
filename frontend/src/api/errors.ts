import type { ApiError } from './types'

/** 接口错误。继承 Error 以保留调用栈，并满足「Promise 只用 Error 拒绝」；字段与 ApiError 一致。 */
export class ApiRequestError extends Error implements ApiError {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly retryAfter: string | null

  constructor(fields: ApiError) {
    super(fields.message)
    this.name = 'ApiRequestError'
    this.status = fields.status
    this.code = fields.code
    this.requestId = fields.requestId
    this.retryAfter = fields.retryAfter ?? null
  }
}

export function isApiError(error: unknown): error is ApiError {
  return Boolean(error && typeof error === 'object' && 'status' in error && 'code' in error && 'message' in error)
}

export function errorMessage(error: unknown, fallback = '请求失败'): string {
  if (isApiError(error)) {
    return error.message || fallback
  }
  if (error instanceof Error) {
    return error.message
  }
  return fallback
}
