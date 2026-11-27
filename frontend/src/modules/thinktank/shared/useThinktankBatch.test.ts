import type { AxiosResponse } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { formatBatchSummary, runConcurrent, useThinktankBatch, type ThinktankBatchItem } from './useThinktankBatch'

const mockDownloadBlob = vi.fn<(blob: Blob, filename: string) => void>()
const mockSuccess = vi.fn<(message: string) => void>()
const mockWarning = vi.fn<(message: string) => void>()
const mockError = vi.fn<(message: string) => void>()
const mockConfirm = vi.fn<(...args: unknown[]) => Promise<string>>()

vi.mock('@/api/download', () => ({
  downloadBlob: (blob: Blob, filename: string) => mockDownloadBlob(blob, filename),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: (message: string) => mockSuccess(message),
    warning: (message: string) => mockWarning(message),
    error: (message: string) => mockError(message),
  },
  ElMessageBox: {
    confirm: (...args: unknown[]) => mockConfirm(...args),
  },
}))

interface TestItem extends ThinktankBatchItem {
  title: string
}

function makeItem(id: string, overrides: Partial<TestItem> = {}): TestItem {
  return {
    id,
    title: `报告-${id}.pdf`,
    is_favorited: false,
    can_edit: true,
    can_export: true,
    ...overrides,
  }
}

describe('useThinktankBatch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('supports custom noun in batch summaries', () => {
    expect(formatBatchSummary('下载', { succeeded: [1, 2], failed: [] }, '报告')).toBe('已下载 2 条报告')
    expect(formatBatchSummary('收藏', { succeeded: [1], failed: [{ item: 2, reason: '超时' }] }, '方案'))
      .toBe('已收藏 1 条，1 条失败（超时）')
    expect(formatBatchSummary('删除', { succeeded: [], failed: [{ item: 1, reason: '无权' }] }, '方案'))
      .toBe('批量删除失败：无权')
  })

  it('handles runConcurrent with minimum concurrency clamp', async () => {
    const res = await runConcurrent([1, 2], async () => {}, 'err', 0)
    expect(res.succeeded).toEqual([1, 2])
    expect(res.failed).toEqual([])
  })

  it('batch downloads exportable rows, respects headers and fallback names, and reports partial failures', async () => {
    const row1 = makeItem('r1', { can_export: true, title: '行业报告.pdf' })
    const row2 = makeItem('r2', { can_export: false, title: '无权报告.pdf' })
    const row3 = makeItem('r3', { can_export: true, title: '方案.pptx' })
    const checked = ref([row1, row2, row3])
    const clearSelection = vi.fn()
    const download = vi.fn<(id: string) => Promise<AxiosResponse<Blob>>>()
      .mockResolvedValueOnce({
        data: new Blob(['pdf']),
        headers: { 'content-disposition': 'attachment; filename="server-r1.pdf"' },
      } as unknown as AxiosResponse<Blob>)
      .mockRejectedValueOnce(new Error('存储不可用'))

    const batch = useThinktankBatch({
      checked,
      clearSelection,
      refresh: vi.fn().mockResolvedValue(undefined),
      itemNoun: '报告',
      api: {
        favorite: vi.fn(),
        unfavorite: vi.fn(),
        remove: vi.fn(),
        download,
        getTitle: row => row.title,
      },
    })

    expect(batch.downloadable.value).toHaveLength(2)
    await batch.onBatchDownload()
    expect(download).toHaveBeenCalledTimes(2)
    expect(download).toHaveBeenCalledWith('r1')
    expect(download).toHaveBeenCalledWith('r3')
    expect(mockDownloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'server-r1.pdf')
    expect(mockWarning).toHaveBeenCalledWith('已下载 1 条，1 条失败（存储不可用）')
    expect(clearSelection).toHaveBeenCalledTimes(1)
  })

  it('uses id fallback title when getTitle is omitted and skips download when api.download is absent', async () => {
    const row = makeItem('x1', { can_export: true })
    const checked = ref([row])
    const download = vi.fn().mockResolvedValue({ data: new Blob(['a']), headers: {} })
    const batch = useThinktankBatch({
      checked,
      clearSelection: vi.fn(),
      refresh: vi.fn().mockResolvedValue(undefined),
      api: { favorite: vi.fn(), unfavorite: vi.fn(), remove: vi.fn(), download },
    })
    await batch.onBatchDownload()
    expect(mockDownloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'x1')
    expect(mockSuccess).toHaveBeenCalledWith('已下载 1 条资料')

    const noDownloadBatch = useThinktankBatch({
      checked,
      clearSelection: vi.fn(),
      refresh: vi.fn().mockResolvedValue(undefined),
      api: { favorite: vi.fn(), unfavorite: vi.fn(), remove: vi.fn() },
    })
    await noDownloadBatch.onBatchDownload()
  })

  it('batch favorites, unfavorites and deletes reports with custom noun', async () => {
    const row = makeItem('r1', { is_favorited: false, can_edit: true })
    const checked = ref([row])
    const refresh = vi.fn().mockResolvedValue(undefined)
    const favorite = vi.fn().mockResolvedValue({ is_favorited: true })
    const unfavorite = vi.fn().mockResolvedValue({ is_favorited: false })
    const remove = vi.fn().mockResolvedValue({ deleted: true })
    mockConfirm.mockResolvedValue('confirm')

    const batch = useThinktankBatch({
      checked,
      clearSelection: vi.fn(),
      refresh,
      itemNoun: '报告',
      api: { favorite, unfavorite, remove },
    })

    await batch.onBatchFavorite()
    expect(row.is_favorited).toBe(true)
    expect(mockSuccess).toHaveBeenCalledWith('已收藏 1 条报告')

    await batch.onBatchUnfavorite(true)
    expect(row.is_favorited).toBe(false)
    expect(refresh).toHaveBeenCalledTimes(1)

    await batch.onBatchDelete()
    expect(remove).toHaveBeenCalledWith('r1')
    expect(mockSuccess).toHaveBeenCalledWith('已删除 1 条报告')
    expect(refresh).toHaveBeenCalledTimes(2)
  })
})
