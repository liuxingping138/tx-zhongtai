import { describe, expect, it } from 'vitest'

import type { ThinktankFavoriteEntry } from '@/api/thinktank'
import {
  applyUnfavoriteUpdate,
  buildFavoriteTabs,
  EMPTY_FAVORITE_COUNTS,
  favoriteRowKey,
  libraryTagType,
  permittedQuickLinks,
} from './favorites'

function makeEntry(overrides: Partial<ThinktankFavoriteEntry> = {}): ThinktankFavoriteEntry {
  return {
    id: 'id-1',
    library: 'knowledge',
    library_label: '资料库',
    title: '行业白皮书.pdf',
    category_label: '产品',
    industry_label: '党政',
    region_label: '北京市',
    file_suffix: 'PDF',
    file_size_display: '1.2 MB',
    favorited_at: '2026-06-01T10:00:00+08:00',
    updated_at: '2026-06-01T10:00:00+08:00',
    can_download: true,
    can_export: true,
    preview_path: '/thinktank/knowledge/id-1',
    ...overrides,
  }
}

describe('我的收藏辅助逻辑', () => {
  it('构建分段标签页与数量徽标', () => {
    expect(buildFavoriteTabs({ all: 6, knowledge: 3, reports: 2, proposals: 1 })).toEqual([
      { key: 'all', label: '全部', count: 6 },
      { key: 'knowledge', label: '资料库', count: 3 },
      { key: 'reports', label: '报告库', count: 2 },
      { key: 'proposals', label: '方案库', count: 1 },
    ])
    expect(EMPTY_FAVORITE_COUNTS).toEqual({ all: 0, knowledge: 0, reports: 0, proposals: 0 })
  })

  it('按来源库返回标签语义颜色与唯一行键', () => {
    expect(libraryTagType('knowledge')).toBe('primary')
    expect(libraryTagType('reports')).toBe('success')
    expect(libraryTagType('proposals')).toBe('warning')
    expect(favoriteRowKey({ library: 'reports', id: '42' })).toBe('reports:42')
  })

  it('取消收藏后立即更新列表、总数与各库计数且不出现负数', () => {
    const e1 = makeEntry({ id: '1', library: 'knowledge' })
    const e2 = makeEntry({ id: '2', library: 'reports', library_label: '报告库', preview_path: '/thinktank/reports/2' })
    const next = applyUnfavoriteUpdate(
      { items: [e1, e2], total: 2, counts: { all: 2, knowledge: 1, reports: 1, proposals: 0 } },
      e1,
    )
    expect(next.items).toEqual([e2])
    expect(next.total).toBe(1)
    expect(next.counts).toEqual({ all: 1, knowledge: 0, reports: 1, proposals: 0 })

    // 目标不在当前列表时原样返回
    const unchanged = applyUnfavoriteUpdate(next, e1)
    expect(unchanged).toBe(next)

    // 计数为 0 时下限保持为 0
    const clamped = applyUnfavoriteUpdate(
      { items: [e2], total: 0, counts: { all: 0, knowledge: 0, reports: 0, proposals: 0 } },
      e2,
    )
    expect(clamped.total).toBe(0)
    expect(clamped.counts).toEqual({ all: 0, knowledge: 0, reports: 0, proposals: 0 })
  })

  it('空状态快捷入口严格按已授权子库过滤', () => {
    expect(permittedQuickLinks(() => true).map(l => l.path)).toEqual([
      '/thinktank/knowledge',
      '/thinktank/reports',
      '/thinktank/proposals',
    ])
    expect(permittedQuickLinks(res => res === 'thinktank.reports').map(l => l.library)).toEqual(['reports'])
    expect(permittedQuickLinks(() => false)).toEqual([])
  })
})
