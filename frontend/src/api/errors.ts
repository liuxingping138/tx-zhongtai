import type { ApiError } from './types'

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
