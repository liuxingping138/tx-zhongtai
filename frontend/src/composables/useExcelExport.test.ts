import { beforeEach, describe, expect, it, vi } from 'vitest'

const download = vi.hoisted(() => vi.fn<(path: string, filename: string, params: unknown) => Promise<void>>())
const message = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))

vi.mock('@/api/download', () => ({ downloadFile: download }))
vi.mock('element-plus', () => ({ ElMessage: message }))

import { useExcelExport } from './useExcelExport'

describe('useExcelExport', () => {
  beforeEach(() => {
    download.mockReset()
    message.success.mockReset()
    message.error.mockReset()
  })

  it('按已生效的筛选导出，并提示已开始下载', async () => {
    download.mockResolvedValue()
    const { onExport, exporting } = useExcelExport({ path: '/x/export', filename: '表.xlsx', filters: () => ({ a: '1' }) })
    await onExport()
    expect(download).toHaveBeenCalledWith('/x/export', '表.xlsx', { a: '1' })
    expect(message.success).toHaveBeenCalledOnce()
    expect(exporting.value).toBe(false)
  })

  it('导出进行中再次点击不会重复下载', async () => {
    let finish!: () => void
    download.mockReturnValue(new Promise<void>((resolve) => { finish = resolve }))
    const { onExport, exporting } = useExcelExport({ path: '/x/export', filename: '表.xlsx', filters: () => ({}) })
    const running = onExport()
    expect(exporting.value).toBe(true)
    await onExport()
    finish()
    await running
    expect(download).toHaveBeenCalledOnce()
  })

  it('失败时提示错误并恢复按钮', async () => {
    download.mockRejectedValue(new Error(''))
    const { onExport, exporting } = useExcelExport({ path: '/x/export', filename: '表.xlsx', filters: () => ({}) })
    await onExport()
    expect(message.error).toHaveBeenCalledWith('下载失败，请重试')
    expect(exporting.value).toBe(false)
  })
})
