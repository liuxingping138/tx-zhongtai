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

// 页面已经拿去提示过的错误。请求层的通用提示（503、409）只给没人处理的错误兜底，免得同一个错误弹两条。
const shown = new WeakSet<object>()

export function markShown(error: unknown): void {
  if (error && typeof error === 'object') shown.add(error)
}

export function wasShown(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && shown.has(error))
}

/** 取给用户看的错误说明。调用它就当页面会自己提示这个错误，请求层不再弹通用提示。 */
export function errorMessage(error: unknown, fallback = '请求失败'): string {
  markShown(error)
  if (isApiError(error)) {
    return error.message || fallback
  }
  if (error instanceof Error) {
    return error.message || fallback
  }
  return fallback
}
