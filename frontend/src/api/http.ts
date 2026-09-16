import axios, { type AxiosResponse } from 'axios'

/**
 * 统一响应包装（与后端 platform_common.responses.ApiResponse 对应）：
 *   { code: string, message: string, data: T | null, request_id: string | null }
 * 失败响应使用同一形状，HTTP 状态码语义见架构文档第 11.1 节。
 */
export interface ApiResponse<T> {
  code: string
  message: string
  data: T | null
  request_id: string | null
}

export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  withCredentials: true, // Refresh Token 走 HttpOnly Cookie
})

http.interceptors.response.use(
  // 拦截器在运行时把响应体解包为 `data.data`，调用方直接拿到业务数据；
  // 为此类型上向下转换为 AxiosResponse，实际类型请参考调用处的显式类型标注。
  (response: AxiosResponse<ApiResponse<unknown>>) => response.data.data as unknown as AxiosResponse,
  (error) => {
    // 401/403/409/422/429/503 的具体交互（单次刷新重试、409 提示重新加载等）
    // 在 P4 阶段接入身份状态后实现，这里只做最基础的错误归一化，避免吞掉错误信息。
    if (error.response) {
      const body = error.response.data as ApiResponse<unknown> | undefined
      return Promise.reject({
        status: error.response.status as number,
        code: body?.code ?? 'UNKNOWN_ERROR',
        message: body?.message ?? '请求失败',
        requestId: body?.request_id ?? null,
      })
    }
    return Promise.reject({ status: 0, code: 'NETWORK_ERROR', message: '网络异常，请检查网络连接', requestId: null })
  },
)
