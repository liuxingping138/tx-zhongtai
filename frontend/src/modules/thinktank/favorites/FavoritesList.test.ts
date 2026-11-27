// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ThinktankFavoriteEntry, ThinktankFavoritesResponse } from '@/api/thinktank'
import FavoritesList from './FavoritesList.vue'

const mockListFavorites = vi.fn<(params?: unknown) => Promise<ThinktankFavoritesResponse>>()
const mockUnfavorite = vi.fn<(lib: string, id: string) => Promise<{ id: string; is_favorited: boolean }>>()
const mockDownload = vi.fn<(lib: string, id: string) => Promise<{ data: Blob; headers: Record<string, string> }>>()
const mockDownloadBlob = vi.fn<(blob: Blob, filename: string) => void>()
const mockCanRead = vi.fn<(res: string) => boolean>()
const mockSuccess = vi.fn<(m: string) => void>()
const mockError = vi.fn<(m: string) => void>()
const mockInfo = vi.fn<(opts: unknown) => { close: () => void }>(() => ({ close: vi.fn() }))

vi.mock('@/api/thinktank', () => ({
  listThinktankFavorites: (params?: unknown) => mockListFavorites(params),
  unfavoriteThinktankItem: (lib: string, id: string) => mockUnfavorite(lib, id),
  downloadThinktankItemBlob: (lib: string, id: string) => mockDownload(lib, id),
}))
vi.mock('@/api/download', () => ({
  downloadBlob: (blob: Blob, filename: string) => { mockDownloadBlob(blob, filename) },
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ canRead: (res: string) => mockCanRead(res) }),
}))
vi.mock('element-plus', () => ({
  ElMessage: {
    success: (m: string) => { mockSuccess(m) },
    error: (m: string) => { mockError(m) },
    info: (opts: unknown) => mockInfo(opts),
  },
}))

const ListPageStub = {
  props: { title: String, total: Number, loading: Boolean, error: String },
  template: '<div class="list-page-stub"><slot name="filters" /><slot /></div>',
}

const RouterLinkStub = {
  props: { to: { type: String, required: true } },
  template: '<a :href="to" class="router-link-stub"><slot /></a>',
}

const FavoritesTableStub = {
  props: { items: { type: Array, default: () => [] } },
  emits: ['download', 'unfavorite'],
  template: `
    <div class="fav-table-stub">
      <div v-for="row in items" :key="row.id" class="fav-row" :data-id="row.id">
        <a class="fav-link" :href="row.preview_path">{{ row.title }}</a>
        <button v-if="row.can_export" type="button" class="btn-download" @click="$emit('download', row)">下载</button>
        <button type="button" class="btn-unfav" @click="$emit('unfavorite', row)">取消收藏</button>
      </div>
    </div>
  `,
}

const ElInputStub = {
  props: { modelValue: { type: String, default: '' } },
  emits: ['update:modelValue', 'clear'],
  template: '<input class="search-input" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
}

const ElButtonStub = {
  emits: ['click'],
  template: '<button @click="$emit(\'click\')"><slot /></button>',
}

function makeEntry(overrides: Partial<ThinktankFavoriteEntry> = {}): ThinktankFavoriteEntry {
  return {
    id: 'k1',
    library: 'knowledge',
    library_label: '资料库',
    title: '行业分析.pdf',
    category_label: '产品',
    industry_label: '党政',
    region_label: '北京市',
    file_suffix: 'PDF',
    file_size_display: '1.2 MB',
    favorited_at: '2026-06-01T10:00:00+08:00',
    updated_at: '2026-06-01T10:00:00+08:00',
    can_export: true,
    preview_path: '/thinktank/knowledge/k1',
    ...overrides,
  }
}

function mountPage() {
  return mount(FavoritesList, {
    global: {
      stubs: {
        ListPage: ListPageStub,
        FavoritesTable: FavoritesTableStub,
        RouterLink: RouterLinkStub,
        TableSkeleton: true,
        'el-input': ElInputStub,
        'el-button': ElButtonStub,
        'el-icon': true,
      },
    },
  })
}

describe('FavoritesList.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCanRead.mockImplementation(res => res === 'thinktank.knowledge' || res === 'thinktank.reports')
  })

  it('渲染分段标签计数、支持切库筛选与关键词搜索', async () => {
    const items = [
      makeEntry({ id: 'k1', library: 'knowledge', can_export: true }),
      makeEntry({ id: 'r1', library: 'reports', library_label: '报告库', title: '交付报告.docx', can_export: false, preview_path: '/thinktank/reports/r1' }),
    ]
    mockListFavorites.mockResolvedValue({
      items,
      total: 2,
      counts: { all: 2, knowledge: 1, reports: 1, proposals: 0 },
    })

    const wrapper = mountPage()
    await flushPromises()

    const tabs = wrapper.findAll('.lib-seg')
    expect(tabs).toHaveLength(4)
    expect(tabs[0]?.text()).toContain('全部')
    expect(tabs[0]?.text()).toContain('2')
    expect(tabs[1]?.text()).toContain('资料库')
    expect(tabs[1]?.text()).toContain('1')
    expect(tabs[2]?.text()).toContain('报告库')
    expect(tabs[2]?.text()).toContain('1')

    await tabs[2]!.trigger('click')
    await flushPromises()
    expect(mockListFavorites).toHaveBeenLastCalledWith({
      library: 'reports',
      keyword: undefined,
      page: 1,
      page_size: 20,
    })

    await wrapper.find('.search-input').setValue('云网')
    await wrapper.find('form.favorites-search').trigger('submit')
    await flushPromises()
    expect(mockListFavorites).toHaveBeenLastCalledWith({
      library: 'reports',
      keyword: '云网',
      page: 1,
      page_size: 20,
    })
  })

  it('支持下载与立即取消收藏并同步更新列表与标签计数', async () => {
    const items = [
      makeEntry({ id: 'k1', library: 'knowledge', can_export: true }),
      makeEntry({ id: 'r1', library: 'reports', library_label: '报告库', can_export: false, preview_path: '/thinktank/reports/r1' }),
    ]
    mockListFavorites.mockResolvedValue({
      items,
      total: 2,
      counts: { all: 2, knowledge: 1, reports: 1, proposals: 0 },
    })
    mockDownload.mockResolvedValue({
      data: new Blob(['pdf']),
      headers: { 'content-disposition': 'attachment; filename="k1.pdf"' },
    })
    mockUnfavorite.mockResolvedValue({ id: 'k1', is_favorited: false })

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.findAll('.btn-download')).toHaveLength(1)
    await wrapper.find('.btn-download').trigger('click')
    await flushPromises()
    expect(mockDownload).toHaveBeenCalledWith('knowledge', 'k1')
    expect(mockDownloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'k1.pdf')

    await wrapper.find('.btn-unfav').trigger('click')
    await flushPromises()
    expect(mockUnfavorite).toHaveBeenCalledWith('knowledge', 'k1')
    expect(wrapper.findAll('.fav-row')).toHaveLength(1)
    const tabs = wrapper.findAll('.lib-seg')
    expect(tabs[0]?.text()).toContain('1')
    expect(tabs[1]?.text()).toContain('0')
    expect(tabs[2]?.text()).toContain('1')
  })

  it('无收藏时渲染空态并只展示已授权子库的快捷入口', async () => {
    mockListFavorites.mockResolvedValue({
      items: [],
      total: 0,
      counts: { all: 0, knowledge: 0, reports: 0, proposals: 0 },
    })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('还没有收藏任何内容')
    const links = wrapper.findAll('.favorites-quick-link')
    expect(links).toHaveLength(2)
    expect(links.map(l => l.attributes('href'))).toEqual(['/thinktank/knowledge', '/thinktank/reports'])
  })
})
