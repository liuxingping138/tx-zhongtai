import type { AxiosResponse } from 'axios'
import { reactive } from 'vue'

import { downloadBlob } from './download'
import { http } from './http'
import type { ApiResponse } from './types'

export { downloadBlob }

export interface ImportResult {
  inserted: number
  updated: number
  skipped: number
  total: number
  report_blob?: Blob
  report_filename?: string
  rejected?: boolean
  skipped_file?: string | null
  /** 结果文件的说明，默认是「校验报告已自动下载」。用户导入的结果文件里是初始密码，需要换个说法。 */
  report_note?: string
}

export type ImportStage = 'upload' | 'parse'

export const importResultUi = reactive({
  visible: false,
  result: null as ImportResult | null,
  filename: '',
  sourceName: '',
})

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
      report_blob: response.data,
      report_filename: filename,
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

export function reportImportResult(result: ImportResult, skippedFilename: string): void {
  if (result.skipped_file) downloadBase64Xlsx(result.skipped_file, skippedFilename)
  importResultUi.result = result
  importResultUi.filename = result.report_filename || skippedFilename
  importResultUi.visible = true
}

export function downloadImportReport(): void {
  const result = importResultUi.result
  if (result?.report_blob) downloadBlob(result.report_blob, importResultUi.filename)
  else if (result?.skipped_file) downloadBase64Xlsx(result.skipped_file, importResultUi.filename)
}

export async function runExcelImport<T>(
  file: File,
  importer: (onProgress: (percent: number, stage: ImportStage) => void) => Promise<T>,
): Promise<T> {
  if (importUi.visible) throw new Error('已有文件正在导入，请等待完成后重试')
  if (!/\.xlsx$/i.test(file.name)) throw new Error('请选择 .xlsx 格式的 Excel 文件')
  if (!file.size) throw new Error('文件为空，请选择包含数据的 Excel 文件')
  importResultUi.visible = false
  importResultUi.result = null
  importResultUi.sourceName = file.name
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
