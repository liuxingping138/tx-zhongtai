import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import type { KnowledgeItem } from '@/api/thinktank'
import { formatBatchSummary, runConcurrent, useKnowledgeBatch } from './useKnowledgeBatch'

const mockFavorite = vi.fn<(id: string) => Promise<{ file_id: string; is_favorited: boolean }>>()
const mockUnfavorite = vi.fn<(id: string) => Promise<{ file_id: string; is_favorited: boolean }>>()
const mockDelete = vi.fn<(id: string) => Promise<{ id: string; deleted: boolean }>>()
const mockDownload = vi.fn<(id: string) => Promise<{ data: Blob; headers: Record<string, string> }>>()
const mockDownloadBlob = vi.fn<(blob: Blob, filename: string) => void>()
const mockSuccess = vi.fn<(message: string) => void>()
const mockWarning = vi.fn<(message: string) => void>()
const mockError = vi.fn<(message: string) => void>()
const mockConfirm = vi.fn<(...args: unknown[]) => Promise<string>>()

vi.mock('@/api/thinktank', () => ({
  favoriteKnowledge: (id: string) => mockFavorite(id),
  unfavoriteKnowledge: (id: string) => mockUnfavorite(id),
  deleteKnowledge: (id: string) => mockDelete(id),
  downloadKnowledgeBlob: (id: string) => mockDownload(id),
}))
vi.mock('@/api/download', () => ({
  downloadBlob: (blob: Blob, filename: string) => { mockDownloadBlob(blob, filename) },
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

function makeItem(id: string, overrides: Partial<KnowledgeItem> = {}): KnowledgeItem {
  return {
    id,
    file_name: `资料-${id}.pdf`,
    file_type: '产品',
    operator_type: '电信',
    depart_affiliation: '',
    industry_type: '党政',
    app_scenario: '',
    market_category: '行客',
    product_type: '云',
    product_sub_type: '',
    prov_name: '北京',
    data_time: '2026-01',
    remark: '',
    file_suffix: 'PDF',
    file_size_bytes: 1024,
    file_size_display: '1 KB',
    uploaded_at: '2026-01-01T00:00:00Z',
    is_defined: true,
    is_favorited: false,
    can_edit: true,
    can_download: true,
    can_export: true,
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    created_by_name: 'admin',
    updated_at: '2026-01-01T00:00:00Z',
    updated_by_name: 'admin',
    ...overrides,
  }
}

describe('useKnowledgeBatch helpers', () => {
  it('runs items in chunks and records partial failures', async () => {
    const items = ['a', 'b', 'c', 'd', 'e']
    const result = await runConcurrent(
      items,
      (item) => (item === 'c' ? Promise.reject(new Error('权限不足')) : Promise.resolve()),
      '默认错误',
      2,
    )
    expect(result.succeeded).toEqual(['a', 'b', 'd', 'e'])
    expect(result.failed).toEqual([{ item: 'c', reason: '权限不足' }])
  })

  it('formats all-success, partial, and all-failure summaries', () => {
    expect(formatBatchSummary('收藏', { succeeded: [1, 2], failed: [] })).toBe('已收藏 2 条资料')
    expect(formatBatchSummary('收藏', { succeeded: [1], failed: [{ item: 2, reason: '网络异常' }] }))
      .toBe('已收藏 1 条，1 条失败（网络异常）')
    expect(formatBatchSummary('删除', { succeeded: [], failed: [{ item: 1, reason: '无权限' }] }))
      .toBe('批量删除失败：无权限')
  })
})

describe('useKnowledgeBatch composable', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('batch favorites only unfavorited items and updates local state', async () => {
    const row1 = makeItem('1', { is_favorited: false })
    const row2 = makeItem('2', { is_favorited: true })
    const checked = ref([row1, row2])
    const clearSelection = vi.fn()
    const refresh = vi.fn().mockResolvedValue(undefined)
    mockFavorite.mockResolvedValue({ file_id: '1', is_favorited: true })

    const batch = useKnowledgeBatch({ checked, clearSelection, refresh })
    expect(batch.unfavorited.value).toHaveLength(1)
    expect(batch.favorited.value).toHaveLength(1)

    await batch.onBatchFavorite()
    expect(mockFavorite).toHaveBeenCalledTimes(1)
    expect(mockFavorite).toHaveBeenCalledWith('1')
    expect(row1.is_favorited).toBe(true)
    expect(mockSuccess).toHaveBeenCalledWith('已收藏 1 条资料')
    expect(clearSelection).toHaveBeenCalledTimes(1)
    expect(refresh).not.toHaveBeenCalled()
  })

  it('skips batch favorite/unfavorite/delete when target list is empty', async () => {
    const checked = ref<KnowledgeItem[]>([])
    const batch = useKnowledgeBatch({ checked, clearSelection: vi.fn(), refresh: vi.fn() })
    await batch.onBatchFavorite()
    await batch.onBatchUnfavorite()
    await batch.onBatchDelete()
    expect(mockFavorite).not.toHaveBeenCalled()
    expect(mockUnfavorite).not.toHaveBeenCalled()
    expect(mockConfirm).not.toHaveBeenCalled()
  })

  it('batch unfavorites with optional refresh and reports partial failure', async () => {
    const row1 = makeItem('1', { is_favorited: true })
    const row2 = makeItem('2', { is_favorited: true })
    const checked = ref([row1, row2])
    const clearSelection = vi.fn()
    const refresh = vi.fn().mockResolvedValue(undefined)
    mockUnfavorite
      .mockResolvedValueOnce({ file_id: '1', is_favorited: false })
      .mockRejectedValueOnce(new Error('服务繁忙'))

    const batch = useKnowledgeBatch({ checked, clearSelection, refresh })
    await batch.onBatchUnfavorite(true)
    expect(row1.is_favorited).toBe(false)
    expect(row2.is_favorited).toBe(true)
    expect(mockWarning).toHaveBeenCalledWith('已取消收藏 1 条，1 条失败（服务繁忙）')
    expect(clearSelection).toHaveBeenCalledTimes(1)
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('batch unfavorite does not refresh when refreshAfter is false', async () => {
    const row1 = makeItem('1', { is_favorited: true })
    const checked = ref([row1])
    const refresh = vi.fn().mockResolvedValue(undefined)
    mockUnfavorite.mockResolvedValue({ file_id: '1', is_favorited: false })

    const batch = useKnowledgeBatch({ checked, clearSelection: vi.fn(), refresh })
    await batch.onBatchUnfavorite(false)
    expect(refresh).not.toHaveBeenCalled()
  })

  it('batch delete cancels cleanly when confirmation is dismissed', async () => {
    const checked = ref([makeItem('1', { can_edit: true })])
    mockConfirm.mockRejectedValue('cancel')

    const batch = useKnowledgeBatch({ checked, clearSelection: vi.fn(), refresh: vi.fn() })
    await batch.onBatchDelete()
    expect(mockDelete).not.toHaveBeenCalled()
  })

  it('batch delete skips non-editable rows, refreshes on success, and reports all-failure errors', async () => {
    const checked = ref([
      makeItem('1', { can_edit: true }),
      makeItem('2', { can_edit: false }),
    ])
    const clearSelection = vi.fn()
    const refresh = vi.fn().mockResolvedValue(undefined)
    mockConfirm.mockResolvedValue('confirm')
    mockDelete.mockResolvedValueOnce({ id: '1', deleted: true })

    const batch = useKnowledgeBatch({ checked, clearSelection, refresh })
    await batch.onBatchDelete()
    expect(mockConfirm).toHaveBeenCalledWith(
      expect.stringContaining('已自动跳过 1 条无删除权限的资料'),
      '批量删除确认',
      expect.any(Object),
    )
    expect(mockDelete).toHaveBeenCalledTimes(1)
    expect(mockDelete).toHaveBeenCalledWith('1')
    expect(mockSuccess).toHaveBeenCalledWith('已删除 1 条资料')
    expect(refresh).toHaveBeenCalledTimes(1)

    // All-failure branch should report error and skip refresh
    refresh.mockClear()
    mockDelete.mockRejectedValueOnce(new Error('文件不存在'))
    await batch.onBatchDelete()
    expect(mockError).toHaveBeenCalledWith('批量删除失败：文件不存在')
    expect(refresh).not.toHaveBeenCalled()
  })

  it('batch downloads downloadable knowledge rows cleanly', async () => {
    const checked = ref([makeItem('1', { can_download: true }), makeItem('2', { can_download: false })])
    const clearSelection = vi.fn()
    mockDownload.mockResolvedValueOnce({
      data: new Blob(['data']),
      headers: { 'content-disposition': 'attachment; filename="k1.pdf"' },
    })

    const batch = useKnowledgeBatch({ checked, clearSelection, refresh: vi.fn() })
    await batch.onBatchDownload()
    expect(mockDownload).toHaveBeenCalledTimes(1)
    expect(mockDownload).toHaveBeenCalledWith('1')
    expect(mockDownloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'k1.pdf')
    expect(mockSuccess).toHaveBeenCalledWith('已下载 1 条资料')
    expect(clearSelection).toHaveBeenCalledTimes(1)
  })
})
