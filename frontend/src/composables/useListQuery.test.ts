import { afterEach, describe, expect, it, type Mock, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
const state = vi.hoisted((): { route: unknown; replace: Mock } => ({ route: null, replace: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => state.route, useRouter: () => ({ replace: state.replace }) }))
import { useListQuery } from './useListQuery'
const scopes: ReturnType<typeof effectScope>[] = []
afterEach(() => { scopes.forEach(scope => scope.stop()); scopes.length = 0; vi.clearAllMocks() })
function setup(initial: Record<string, unknown> = {}) {
  const route = reactive({ path: '/list', query: initial })
  state.route = route
  state.replace.mockImplementation(async (target: {query: Record<string, unknown>}) => { route.query = target.query; await nextTick() })
  const query = reactive({ keyword: '', username: '', range: [] as string[], page: 1, page_size: 20 })
  const reload = vi.fn(async () => {})
  const scope = effectScope(); scopes.push(scope)
  const sync = scope.run(() => useListQuery(query, reload, ['username']))!
  return { route, query, reload, sync }
}
describe('committed list navigation', () => {
  it('restores filters, range and paging, excluding private fields', () => {
    const { query } = setup({ keyword: '政策', range: ['2026-01-01', '2026-02-01'], page: '3', page_size: '50', username: 'private' })
    expect(query).toEqual({ keyword: '政策', username: '', range: ['2026-01-01', '2026-02-01'], page: 3, page_size: 50 })
  })
  it('rejects invalid paging values', () => {
    const { query } = setup({ page: '-3', page_size: '999' })
    expect(query.page).toBe(1); expect(query.page_size).toBe(20)
  })
  it('does not save keystrokes and commits without triggering a duplicate request', async () => {
    const { query, route, sync, reload } = setup()
    query.keyword = '产业'; query.page = 2; query.username = 'private'
    await nextTick(); expect(state.replace).not.toHaveBeenCalled()
    await sync.commit()
    expect(route.query).toEqual({ keyword: '产业', page: '2' })
    expect(reload).not.toHaveBeenCalled()
    route.query = { page: '2', keyword: '产业' }
    await nextTick()
    expect(reload).not.toHaveBeenCalled()
  })
  it('counts only captured filters, not in-progress keystrokes', () => {
    const { query, sync } = setup({ keyword: '已查询' })
    expect(sync.applied.keyword).toBe('已查询')
    query.keyword = '尚未查询'
    expect(sync.applied.keyword).toBe('已查询')
    sync.captureApplied()
    expect(sync.applied.keyword).toBe('尚未查询')
  })
  it('keeps uncommitted filters out of paging requests and the url', async () => {
    const { query, route, sync, reload } = setup({ keyword: '已查询', page: '2' })
    query.keyword = '草稿'
    query.page = 3
    const params = sync.requested()
    expect(params.keyword).toBe('已查询')
    expect(params.page).toBe(3)
    await sync.commitPage()
    expect(route.query).toEqual({ keyword: '已查询', page: '3' })
    expect(query.keyword).toBe('草稿')
    expect(sync.applied.keyword).toBe('已查询')
    expect(reload).not.toHaveBeenCalled()
  })
  it('applies a status card toggle without adopting other drafts', () => {
    const { query, sync } = setup({ keyword: '已查询', range: ['关注'] })
    query.keyword = '草稿'
    sync.replaceApplied('range', ['停更'])
    expect(sync.applied.range).toEqual(['停更'])
    expect(sync.applied.keyword).toBe('已查询')
    expect(query.keyword).toBe('草稿')
    expect(query.range).toEqual(['停更'])
    expect(query.page).toBe(1)
  })
  it('restores browser navigation and ignores a different route', async () => {
    const { query, route, reload } = setup({ keyword: '旧条件' })
    route.query = { page: '4' }; await nextTick()
    expect(query.keyword).toBe(''); expect(query.page).toBe(4); expect(reload).toHaveBeenCalledTimes(1)
    route.path = '/other'; route.query = { keyword: '其他页' }; await nextTick()
    expect(query.keyword).toBe(''); expect(reload).toHaveBeenCalledTimes(1)
  })
  it('查询回到第一页，把输入框里的条件变成已生效条件再加载', () => {
    const { query, sync, reload } = setup({ page: '3' })
    query.keyword = '新条件'
    sync.search()
    expect(query.page).toBe(1)
    expect(sync.applied.keyword).toBe('新条件')
    expect(reload).toHaveBeenCalledOnce()
  })
  it('重置把筛选恢复成初始值，每页条数保持不变', () => {
    const { query, sync, reload } = setup({ keyword: '旧条件', range: ['2026-01-01', '2026-02-01'], page: '2', page_size: '50' })
    sync.resetFilters()
    expect(query).toEqual({ keyword: '', username: '', range: [], page: 1, page_size: 50 })
    expect(sync.applied.keyword).toBe('')
    expect(reload).toHaveBeenCalledOnce()
  })
})
