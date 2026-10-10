import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const httpMock = vi.hoisted(() => ({ post: vi.fn() }))
const download = vi.hoisted(() => ({ downloadBlob: vi.fn() }))
vi.mock('./http', () => ({ http: httpMock }))
vi.mock('./download', () => download)

import {
  downloadImportReport,
  importResultUi,
  importUi,
  postExcelImport,
  reportImportResult,
  runExcelImport,
} from './excelImport'

const xlsxFile = (name = 'a.xlsx', size = 10) => ({ name, size }) as File
const xlsxType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

beforeEach(() => {
  httpMock.post.mockReset()
  download.downloadBlob.mockReset()
  importUi.visible = false
  importResultUi.visible = false
  importResultUi.result = null
})

afterEach(() => vi.unstubAllGlobals())

describe('runExcelImport', () => {
  it.each([
    ['已有文件正在导入', () => { importUi.visible = true; return xlsxFile() }],
    ['.xlsx', () => xlsxFile('a.csv')],
    ['文件为空', () => xlsxFile('a.xlsx', 0)],
  ])('不满足条件时拒绝：%s', async (message, make) => {
    const importer = vi.fn()
    await expect(runExcelImport(make(), importer)).rejects.toThrow(message)
    expect(importer).not.toHaveBeenCalled()
  })

  it('导入期间显示进度，结束后无论成败都复位', async () => {
    const seen: number[] = []
    await runExcelImport(xlsxFile('数据.XLSX'), (onProgress) => {
      expect(importUi.visible).toBe(true)
      expect(importUi.fileName).toBe('数据.XLSX')
      onProgress(40, 'upload')
      seen.push(importUi.percent)
      return Promise.resolve('ok')
    })
    expect(seen).toEqual([40])
    expect(importUi).toMatchObject({ visible: false, percent: 0, fileName: '', stage: 'upload' })
    await expect(runExcelImport(xlsxFile(), () => Promise.reject(new Error('boom')))).rejects.toThrow('boom')
    expect(importUi.visible).toBe(false)
  })

  it('开始新导入时清掉上一次的结果', async () => {
    importResultUi.visible = true
    importResultUi.result = { inserted: 1, updated: 0, skipped: 0, total: 1 }
    await runExcelImport(xlsxFile(), () => Promise.resolve(null))
    expect(importResultUi.visible).toBe(false)
    expect(importResultUi.result).toBeNull()
  })
})

describe('postExcelImport', () => {
  const blobOf = (content: string) => new Blob([content])

  it('后端返回校验报告时自动下载，并从响应头读出统计', async () => {
    httpMock.post.mockResolvedValue({
      data: blobOf('xlsx'),
      headers: {
        'content-type': xlsxType,
        'content-disposition': "attachment; filename*=UTF-8''%E6%A0%A1%E9%AA%8C.xlsx",
        'x-import-inserted': '0',
        'x-import-skipped': '3',
        'x-import-total': '5',
        'x-import-rejected': '1',
      },
    })
    const result = await postExcelImport('/x/import', xlsxFile())
    expect(download.downloadBlob).toHaveBeenCalledWith(expect.any(Blob), '校验.xlsx')
    expect(result).toMatchObject({ inserted: 0, skipped: 3, total: 5, rejected: true, report_filename: '校验.xlsx' })
  })

  it('普通文件名和缺失的头都有兜底', async () => {
    httpMock.post.mockResolvedValue({
      data: blobOf('x'),
      headers: { 'content-type': 'application/octet-stream', 'content-disposition': 'attachment; filename="plain.xlsx"' },
    })
    const result = await postExcelImport('/x/import', xlsxFile())
    expect(result).toMatchObject({ report_filename: 'plain.xlsx', inserted: 0, total: 0, rejected: false })
    httpMock.post.mockResolvedValue({ data: blobOf('x'), headers: { 'content-type': xlsxType } })
    expect((await postExcelImport('/x/import', xlsxFile())).report_filename).toBe('上传校验.xlsx')
  })

  it('没有报告文件时解析 JSON 信封', async () => {
    const body = { code: 'OK', data: { inserted: 4, updated: 0, skipped: 0, total: 4 } }
    httpMock.post.mockResolvedValue({ data: blobOf(JSON.stringify(body)), headers: { 'content-type': 'application/json' } })
    expect(await postExcelImport('/x/import', xlsxFile())).toEqual(body.data)
    expect(download.downloadBlob).not.toHaveBeenCalled()
  })

  it('上传进度：传完显示解析阶段，进度最多 99', async () => {
    const stages: [number, string][] = []
    httpMock.post.mockImplementation((_url: string, _form: unknown, options: { onUploadProgress: (e: object) => void }) => {
      options.onUploadProgress({ loaded: 0, total: 0 })
      options.onUploadProgress({ loaded: 50, total: 100 })
      options.onUploadProgress({ loaded: 99.9, total: 100 })
      options.onUploadProgress({ loaded: 100, total: 100 })
      return Promise.resolve({ data: blobOf(JSON.stringify({ data: {} })), headers: { 'content-type': 'application/json' } })
    })
    await postExcelImport('/x/import', xlsxFile(), (percent, stage) => stages.push([percent, stage]))
    expect(stages).toEqual([[0, 'upload'], [50, 'upload'], [99, 'upload'], [100, 'parse']])
  })
})

describe('结果与报告下载', () => {
  it('跳过明细是 base64 时解码后触发浏览器下载', () => {
    const clicked: string[] = []
    const link = { href: '', download: '', click: () => clicked.push(link.download) }
    vi.stubGlobal('document', { createElement: () => link })
    vi.stubGlobal('URL', { createObjectURL: () => 'blob:x', revokeObjectURL: vi.fn() })
    reportImportResult({ inserted: 1, updated: 0, skipped: 1, total: 2, skipped_file: btoa('hello') }, '跳过.xlsx')
    expect(clicked).toEqual(['跳过.xlsx'])
    expect(importResultUi).toMatchObject({ visible: true, filename: '跳过.xlsx' })
  })

  it('没有跳过明细只展示结果；报告文件名优先用后端给的', () => {
    reportImportResult({ inserted: 1, updated: 0, skipped: 0, total: 1, report_filename: '服务端.xlsx' }, '默认.xlsx')
    expect(importResultUi.filename).toBe('服务端.xlsx')
  })

  it('重新下载报告：有报告文件用报告文件，没有再用 base64', () => {
    const blob = new Blob(['r'])
    importResultUi.result = { inserted: 0, updated: 0, skipped: 1, total: 1, report_blob: blob }
    importResultUi.filename = '报告.xlsx'
    downloadImportReport()
    expect(download.downloadBlob).toHaveBeenCalledWith(blob, '报告.xlsx')
  })
})
