import { afterEach, describe, expect, it, type Mock, vi } from 'vitest'
import { effectScope, nextTick, reactive, ref } from 'vue'

const mocks = vi.hoisted((): {
  route: { path: string; query: Record<string, unknown> }
  replace: Mock
  get: Mock
  post: Mock
  patch: Mock
  delete: Mock
  postExcelImport: Mock
  fetchFilterOptions: Mock
  searchFilterOptions: Mock
} => ({
  route: { path: '/codebook/thinktank/file-types', query: {} },
  replace: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  postExcelImport: vi.fn(),
  fetchFilterOptions: vi.fn(),
  searchFilterOptions: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ replace: mocks.replace }),
}))

vi.mock('@/api/http', () => ({
  http: {
    get: mocks.get,
    post: mocks.post,
    patch: mocks.patch,
    delete: mocks.delete,
  },
  request: <T>(promise: Promise<T>) => promise,
}))

vi.mock('@/api/excelImport', () => ({
  postExcelImport: mocks.postExcelImport,
}))

vi.mock('@/api/filterOptions', () => ({
  fetchFilterOptions: mocks.fetchFilterOptions,
  searchFilterOptions: mocks.searchFilterOptions,
}))

import {
  createThinktankDict,
  deleteThinktankDict,
  importThinktankDicts,
  listThinktankDicts,
  updateThinktankDict,
  type ThinktankDictSlug,
} from '@/api/codebook'
import {
  getThinktankDictConfig,
  isThinktankDictSlug,
  resolveThinktankDictSlug,
  THINKTANK_DICT_CONFIGS,
  THINKTANK_DICT_SLUGS,
  thinktankDictBasePath,
  thinktankDictExportFilename,
  thinktankDictExportPath,
  thinktankDictSkippedFilename,
} from './configs'
import { normalizeFilterOptions, useThinktankDictOptions } from './useThinktankDictOptions'
import { useThinktankDictQuery } from './useThinktankDictQuery'

const scopes: ReturnType<typeof effectScope>[] = []

afterEach(() => {
  scopes.forEach(scope => scope.stop())
  scopes.length = 0
  vi.clearAllMocks()
})

describe('智库 6 张专属码表配置 configs.ts', () => {
  it('完整定义全部 6 个 slug 及其元数据', () => {
    expect(THINKTANK_DICT_SLUGS).toEqual([
      'file-types',
      'departments',
      'industries',
      'product-types',
      'provinces',
      'market-categories',
    ])
    expect(Object.keys(THINKTANK_DICT_CONFIGS)).toHaveLength(6)

    const expected: Record<ThinktankDictSlug, { title: string; resource: string; fieldLabel: string; hint: string }> = {
      'file-types': {
        title: '文件类别码表',
        resource: 'codebook.thinktank_file_types',
        fieldLabel: '文件类别',
        hint: '维护智库资料库的文件类别枚举，供智库筛选与打标使用。',
      },
      departments: {
        title: '客户部门归属码表',
        resource: 'codebook.thinktank_departments',
        fieldLabel: '客户部门归属',
        hint: '维护智库使用的客户部门归属枚举，供智库各子库选用。',
      },
      industries: {
        title: '行业类别码表',
        resource: 'codebook.thinktank_industries',
        fieldLabel: '行业类别',
        hint: '维护智库使用的行业类别枚举，供智库筛选与打标使用。',
      },
      'product-types': {
        title: '产品类别码表',
        resource: 'codebook.thinktank_product_types',
        fieldLabel: '产品类别',
        hint: '维护智库使用的产品类别枚举，供智库资料库选用。',
      },
      provinces: {
        title: '省份码表',
        resource: 'codebook.thinktank_provinces',
        fieldLabel: '省份名称',
        hint: '维护智库专属省份码表（含集团及全国 31 省），智库所有省份字段统一引用本码表。',
      },
      'market-categories': {
        title: '市场类别码表',
        resource: 'codebook.thinktank_market_categories',
        fieldLabel: '市场类别',
        hint: '维护智库使用的市场类别枚举，供智库资料库选用。',
      },
    }

    for (const slug of THINKTANK_DICT_SLUGS) {
      const cfg = getThinktankDictConfig(slug)
      expect(cfg).toEqual({ slug, ...expected[slug] })
      expect(thinktankDictBasePath(slug)).toBe(`/codebook/thinktank/${slug}`)
      expect(thinktankDictExportPath(slug)).toBe(`/codebook/thinktank/${slug}/export`)
      expect(thinktankDictExportFilename(cfg)).toBe(`${expected[slug].title}.xlsx`)
      expect(thinktankDictSkippedFilename(cfg)).toBe(`${expected[slug].fieldLabel}-跳过明细.xlsx`)
    }
  })

  it('校验并按优先级解析 slug（props 优先于 route.meta.dictSlug，无效值回落默认）', () => {
    expect(isThinktankDictSlug('provinces')).toBe(true)
    expect(isThinktankDictSlug('unknown')).toBe(false)
    expect(isThinktankDictSlug(null)).toBe(false)

    expect(resolveThinktankDictSlug('provinces', 'departments')).toBe('provinces')
    expect(resolveThinktankDictSlug(undefined, 'industries')).toBe('industries')
    expect(resolveThinktankDictSlug(undefined, 'invalid-slug')).toBe('file-types')
    expect(resolveThinktankDictSlug(undefined, undefined)).toBe('file-types')
  })
})

describe('codebook.ts 智库码表 API 封装', () => {
  it('按约定方法与路径调用 list/create/update/delete/import', async () => {
    mocks.get.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20 })
    await listThinktankDicts('provinces', { keyword: ['广东省'], page: 2, page_size: 50 })
    expect(mocks.get).toHaveBeenCalledWith('/codebook/thinktank/provinces', {
      params: { keyword: ['广东省'], page: 2, page_size: 50 },
    })

    mocks.post.mockResolvedValueOnce({ id: '1', name: '集团' })
    await createThinktankDict('provinces', { name: '集团', sort_order: 1 })
    expect(mocks.post).toHaveBeenCalledWith('/codebook/thinktank/provinces', { name: '集团', sort_order: 1 })

    mocks.patch.mockResolvedValueOnce({ id: '1', name: '广东省', version: 2 })
    await updateThinktankDict('provinces', '1', { name: '广东省', version: 1 })
    expect(mocks.patch).toHaveBeenCalledWith('/codebook/thinktank/provinces/1', { name: '广东省', version: 1 })

    mocks.delete.mockResolvedValueOnce({ deleted: true })
    await deleteThinktankDict('provinces', '1')
    expect(mocks.delete).toHaveBeenCalledWith('/codebook/thinktank/provinces/1')

    const file = new File(['xlsx'], 'provinces.xlsx')
    const onProgress = vi.fn()
    mocks.postExcelImport.mockResolvedValueOnce({ inserted: 1, updated: 0, skipped: 0, total: 1 })
    await importThinktankDicts('provinces', file, onProgress)
    expect(mocks.postExcelImport).toHaveBeenCalledWith('/codebook/thinktank/provinces/import', file, onProgress)
  })
})

describe('useThinktankDictOptions 动态路径筛选项', () => {
  it('兼容标准 FilterOptionsPayload、数组精简返回及非法载荷', () => {
    expect(normalizeFilterOptions(null)).toEqual({})
    expect(normalizeFilterOptions('bad')).toEqual({})
    expect(normalizeFilterOptions({ options: { name: { items: ['经分', 123], truncated: true }, ignored: 42 } })).toEqual({
      name: { items: ['经分'], truncated: true },
    })
    expect(normalizeFilterOptions({ name: ['集团', '广东省'] })).toEqual({
      name: ['集团', '广东省'].length ? { items: ['集团', '广东省'], truncated: false } : {},
    })
    expect(normalizeFilterOptions({ options: { name: ['云', '网'] } })).toEqual({
      name: { items: ['云', '网'], truncated: false },
    })
  })

  it('截断字段提供服务端搜索，路径切换后清空旧项并丢弃过时响应', async () => {
    let resolveFirst!: (val: unknown) => void
    mocks.fetchFilterOptions
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce({ options: { name: { items: ['广东省', '浙江省'], truncated: true } } })
    mocks.searchFilterOptions.mockResolvedValueOnce({ items: ['广东省'] })

    const path = ref('/codebook/thinktank/file-types')
    const scope = effectScope()
    scopes.push(scope)
    const options = scope.run(() => useThinktankDictOptions(path))!

    const firstLoad = options.load()
    path.value = '/codebook/thinktank/provinces'
    options.reset()
    expect(options.bind('name')).toEqual({ options: [] })

    await options.load()
    resolveFirst({ options: { name: { items: ['经分'], truncated: false } } })
    await firstLoad

    const binding = options.bind('name')
    expect(binding.options).toEqual(['广东省', '浙江省'])
    expect(binding.remoteSearch).toBeTypeOf('function')
    expect(await binding.remoteSearch?.('广')).toEqual(['广东省'])
    expect(mocks.searchFilterOptions).toHaveBeenCalledWith('/codebook/thinktank/provinces', 'name', '广')
  })

  it('接口失败时静默降级而不抛异常', async () => {
    mocks.fetchFilterOptions.mockRejectedValueOnce(new Error('network error'))
    const path = ref('/codebook/thinktank/industries')
    const scope = effectScope()
    scopes.push(scope)
    const options = scope.run(() => useThinktankDictOptions(path))!

    await expect(options.load()).resolves.toBeUndefined()
    expect(options.loaded.value).toBe(false)
    expect(options.bind('name')).toEqual({ options: [] })
  })
})

describe('useThinktankDictQuery 路由参数同步与跨码表切换', () => {
  it('从路由恢复合法筛选与分页、忽略非法分页值，并在跨码表切换后继续同步新路径', async () => {
    const route = reactive<{ path: string; query: Record<string, unknown> }>({
      path: '/codebook/thinktank/file-types',
      query: { keyword: '经分', page: '2', page_size: '999' },
    })
    mocks.route = route
    mocks.replace.mockImplementation((target: { path: string; query: Record<string, unknown> }) => {
      route.query = target.query
      return Promise.resolve()
    })
    const reload = vi.fn(() => Promise.resolve())
    const scope = effectScope()
    scopes.push(scope)
    const state = scope.run(() => useThinktankDictQuery(reload))!

    expect(state.query).toEqual({ keyword: ['经分'], page: 2, page_size: 20 })
    expect(state.requested()).toEqual({ keyword: ['经分'], page: 2, page_size: 20 })

    // 浏览器后退同路径触发 reload
    route.query = { keyword: ['通报'], page: '3', page_size: '50' }
    await nextTick()
    expect(state.query).toEqual({ keyword: ['通报'], page: 3, page_size: 50 })
    expect(reload).toHaveBeenCalledTimes(1)

    // 切到另一张码表路由后更新 currentPath 并支持继续 commitPage
    route.path = '/codebook/thinktank/provinces'
    route.query = { keyword: ['广东省'] }
    state.syncForSlugChange()
    expect(state.query).toEqual({ keyword: ['广东省'], page: 1, page_size: 20 })

    state.query.page = 2
    state.query.page_size = 50
    await state.commitPage()
    expect(mocks.replace).toHaveBeenCalledWith({
      path: '/codebook/thinktank/provinces',
      query: { keyword: ['广东省'], page: '2', page_size: '50' },
    })
  })
})
