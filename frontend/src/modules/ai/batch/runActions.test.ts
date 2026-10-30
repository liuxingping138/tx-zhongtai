import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { BatchRun } from '@/api/ai'

const confirm = vi.hoisted(() => vi.fn<() => Promise<unknown>>())
const message = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
const api = vi.hoisted(() => ({ stopBatchRun: vi.fn(), retryBatchRun: vi.fn(), deleteBatchRun: vi.fn(), runAllBatchRun: vi.fn() }))
const download = vi.hoisted(() => vi.fn())
vi.mock('element-plus', () => ({ ElMessageBox: { confirm }, ElMessage: message }))
vi.mock('@/api/ai', () => api)
vi.mock('../shared/downloads', () => ({ downloadBatchFile: download }))

import { deleteRun, downloadRunFile, retryRun, runAllRun, stopRun } from './runActions'

const run = { id: 'r1', prompt_title: '政策解读', model_name: '模型', failed_count: 2, total_count: 10, done_count: 8, pending_count: 4 } as BatchRun

describe('批量任务的操作', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const fn of Object.values(api)) fn.mockResolvedValue({})
  })

  it('取消确认时什么都不做', async () => {
    confirm.mockRejectedValue('cancel')
    expect(await stopRun(run)).toBe(false)
    expect(await deleteRun(run)).toBe(false)
    expect(api.stopBatchRun).not.toHaveBeenCalled()
    expect(api.deleteBatchRun).not.toHaveBeenCalled()
  })

  it('重跑前写明要重跑几条、为什么，确认后排队', async () => {
    confirm.mockResolvedValue(true)
    expect(await retryRun(run)).toBe(true)
    expect(confirm.mock.calls[0]).toEqual(expect.arrayContaining([expect.stringContaining('重新提问 4 条（失败 2 条、没跑到 2 条）')]))
    expect(api.retryBatchRun).toHaveBeenCalledWith('r1')
    expect(message.success).toHaveBeenCalledWith('已加入队列，重跑 4 条')
  })

  it('跑全部前说清沿用哪些、按这次单条费用估算，排队后说共几条、沿用几条', async () => {
    confirm.mockResolvedValue(true)
    api.runAllBatchRun.mockResolvedValue({ total_count: 500, reused_rows: 8 })
    const tested = { ...run, input_name: '企业.xlsx', row_limit: 10, done_count: 10, inference_cost: 0.5, search_cost: 0 }
    expect(await runAllRun(tested)).toBe(true)
    expect(confirm.mock.calls[0]).toEqual(expect.arrayContaining([expect.stringContaining('前 10 行里答好的沿用、不再花钱')]))
    expect(confirm.mock.calls[0]).toEqual(expect.arrayContaining([expect.stringContaining('按这次每条约 ¥0.0500 估算')]))
    expect(api.runAllBatchRun).toHaveBeenCalledWith('r1')
    expect(message.success).toHaveBeenCalledWith('已加入队列，共 500 条，沿用 8 条')
  })

  it('接口失败时提示并返回 false，调用方不刷新', async () => {
    confirm.mockResolvedValue(true)
    api.stopBatchRun.mockRejectedValue(new Error('x'))
    api.deleteBatchRun.mockRejectedValue(new Error('x'))
    api.retryBatchRun.mockRejectedValue(new Error('x'))
    expect(await stopRun(run)).toBe(false)
    expect(await deleteRun(run)).toBe(false)
    expect(await retryRun(run)).toBe(false)
    expect(message.error).toHaveBeenCalledTimes(3)
  })

  it('停止、删除成功返回 true；下载文件名带模板名', async () => {
    confirm.mockResolvedValue(true)
    expect(await stopRun(run)).toBe(true)
    expect(await deleteRun(run)).toBe(true)
    await downloadRunFile(run, 'result')
    expect(download).toHaveBeenCalledWith('r1', 'result', '政策解读-结果.xlsx')
    download.mockRejectedValue(new Error('x'))
    await downloadRunFile(run, 'log')
    expect(message.error).toHaveBeenCalledTimes(1)
  })
})
