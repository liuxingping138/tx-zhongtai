import type { AxiosResponse } from 'axios'

import { http } from './http'

/**
 * 触发浏览器下载。
 *
 * 链接必须先挂到文档里再点击，且 objectURL 要延后释放：
 * 立即 revoke 在部分浏览器上会让下载拿不到数据。
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.hidden = true
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * 下载服务端导出的文件。
 *
 * 走 http 实例而不是裸 fetch：这样才能复用 401 自动续期、
 * CSRF/Authorization 请求头和统一的中文错误提示。裸 fetch 会把
 * 这些全部绕开——令牌过期时导出只会一直失败，
 * 而且 403／503 都被压成同一句无信息的「导出失败」。
 */
export async function downloadFile(path: string, filename: string, timeout = 600_000): Promise<void> {
  const response = (await http.get(path, { responseType: 'blob', timeout })) as unknown as AxiosResponse<Blob>
  downloadBlob(response.data, filename)
}
