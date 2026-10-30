import { beforeEach, describe, expect, it, vi } from 'vitest'

const message = vi.hoisted(() => Object.assign(vi.fn(() => ({ close: vi.fn() })), { info: vi.fn() }))
const downloadFile = vi.hoisted(() => vi.fn())
vi.mock('element-plus', () => ({ ElMessage: message }))
vi.mock('@/api/download', () => ({ downloadFile }))

import { downloadBatchFile, downloadBatchInputTemplate } from './downloads'

describe('AI 产物下载', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('准备期间一直提示，同一个文件再点只提醒、不重复下载，结束后可以再下', async () => {
    let finish: () => void = () => undefined
    downloadFile.mockReturnValue(new Promise<void>(resolve => { finish = resolve }))
    const first = downloadBatchFile('r1', 'raw', '原始返回.csv')
    await downloadBatchFile('r1', 'raw', '原始返回.csv')
    expect(downloadFile).toHaveBeenCalledOnce()
    expect(message.info).toHaveBeenCalledWith('「原始返回.csv」正在准备，下载开始前不用再点')
    const notice = message.mock.results[0]?.value as { close: () => void }
    finish()
    await first
    expect(notice.close).toHaveBeenCalled()

    downloadFile.mockResolvedValue(undefined)
    await downloadBatchFile('r1', 'raw', '原始返回.csv')
    expect(downloadFile).toHaveBeenCalledTimes(2)
  })

  it('下载失败也收起提示，错误交给调用方说', async () => {
    downloadFile.mockRejectedValue(new Error('断网'))
    await expect(downloadBatchInputTemplate('p1', 'draft', '数据模板.xlsx')).rejects.toThrow('断网')
    expect(downloadFile).toHaveBeenCalledWith('/ai/batch-runs/input-template', '数据模板.xlsx', { prompt_id: 'p1', version: 'draft' })
    await expect(downloadBatchInputTemplate('p1', 'draft', '数据模板.xlsx')).rejects.toThrow('断网')
    expect(downloadFile).toHaveBeenCalledTimes(2)
  })
})
