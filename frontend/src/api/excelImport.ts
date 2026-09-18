import type { AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import { reactive } from 'vue'

import { http } from './http'
import type { ApiResponse } from './types'

export interface ImportResult {
  inserted: number
  updated: number
  skipped: number
  total: number
  rejected?: boolean
  skipped_file?: string | null
}

export type ImportStage = 'upload' | 'parse'

export const importUi = reactive({
  visible: false,
  fileName: '',
  percent: 0,
  stage: 'upload' as ImportStage,
})

function headerValue(headers: AxiosResponse['headers'], name: string): string {
  const value = headers[name] ?? headers[name.toLowerCase()]
  return value == null ? '' : String(value)
}

function filenameFromDisposition(value: string, fallback: string): string {
  const utf = /filename\*=UTF-8''([^;]+)/i.exec(value)
  if (utf?.[1]) {
    return decodeURIComponent(utf[1])
  }
  const ascii = /filename="?([^"]+)"?/i.exec(value)
  return ascii?.[1] || fallback
}

export async function postExcelImport(
  url: string,
  file: File,
  onProgress?: (percent: number, stage: ImportStage) => void,
  timeout = 600_000,
): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  const response = (await http.post(url, form, {
    timeout,
    responseType: 'blob',
    onUploadProgress(event) {
      if (!event.total) {
        onProgress?.(0, 'upload')
        return
      }
      const percent = Math.round((event.loaded / event.total) * 100)
      if (event.loaded >= event.total) {
        onProgress?.(100, 'parse')
        return
      }
      onProgress?.(Math.min(percent, 99), 'upload')
    },
  })) as AxiosResponse<Blob>
  const contentType = headerValue(response.headers, 'content-type')
  if (contentType.includes('spreadsheetml') || contentType.includes('octet-stream')) {
    const filename = filenameFromDisposition(headerValue(response.headers, 'content-disposition'), '上传校验.xlsx')
    downloadBlob(response.data, filename)
    return {
      inserted: Number(headerValue(response.headers, 'x-import-inserted') || 0),
      updated: Number(headerValue(response.headers, 'x-import-updated') || 0),
      skipped: Number(headerValue(response.headers, 'x-import-skipped') || 0),
      total: Number(headerValue(response.headers, 'x-import-total') || 0),
      rejected: headerValue(response.headers, 'x-import-rejected') === '1',
    }
  }
  const body = JSON.parse(await response.data.text()) as ApiResponse<ImportResult>
  return body.data as ImportResult
}

export function downloadBase64Xlsx(content: string, filename: string): void {
  const binary = atob(content)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  const url = URL.createObjectURL(
    new Blob([bytes], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function reportImportResult(result: ImportResult, skippedFilename: string): void {
  if (result.rejected) {
    if (result.skipped_file) {
      downloadBase64Xlsx(result.skipped_file, skippedFilename)
    }
    ElMessage.warning(
      `未通过校验（重复或省市区编码为空），本次未入库。完整打标文件已下载，修正后再上传。`,
    )
    return
  }
  if (result.skipped) {
    if (result.skipped_file) {
      downloadBase64Xlsx(result.skipped_file, skippedFilename)
    }
    ElMessage.warning(
      `导入完成：新增 ${result.inserted}，跳过 ${result.skipped}。跳过明细已下载，可查看「校验说明」。`,
    )
    return
  }
  if (result.updated) {
    ElMessage.success(`导入完成：新增 ${result.inserted}，更新 ${result.updated}，跳过 ${result.skipped}`)
    return
  }
  ElMessage.success(`导入完成：新增 ${result.inserted}，跳过 ${result.skipped}`)
}

export async function runExcelImport<T>(
  file: File,
  importer: (onProgress: (percent: number, stage: ImportStage) => void) => Promise<T>,
): Promise<T> {
  importUi.visible = true
  importUi.fileName = file.name
  importUi.percent = 0
  importUi.stage = 'upload'
  try {
    return await importer((percent, stage) => {
      importUi.percent = percent
      importUi.stage = stage
    })
  } finally {
    importUi.visible = false
    importUi.percent = 0
    importUi.fileName = ''
    importUi.stage = 'upload'
  }
}
