import { afterEach, describe, expect, it, vi } from 'vitest'
import { initialQuery, type TenderQuery } from './fields'
import { MAX_COUNT_POLLS, useTenderList } from './useTenderList'
import type { TenderPage } from '@/api/tender'

const api = vi.hoisted(() => ({ list: vi.fn(), count: vi.fn() }))
vi.mock('@/api/tender', () => ({ listTenderRecords: api.list, getTenderCount: api.count }))
vi.mock('vue', async importOriginal => ({ ...await importOriginal<typeof import('vue')>(), onBeforeUnmount: vi.fn() }))
const setup = (override?: () => TenderQuery) =>
  useTenderList('winbid', { requested: override ?? initialQuery, commitPage: () => Promise.resolve() })
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers() })

describe('招中标列表与后台计数', () => {
  it('列表先返回，计数并行拉取并在完成后单独补充', async () => {
    vi.useFakeTimers()
    api.list.mockResolvedValue({ items: [], has_more: true })
    api.count.mockResolvedValueOnce({ state: 'pending', data: null }).mockResolvedValueOnce({ state: 'ready', data: { total: 23968892 } })
    const loader = setup()
    await loader.load()
    expect(loader.loading.value).toBe(false)
    expect(loader.total.value).toBeNull()
    await vi.advanceTimersByTimeAsync(3000)
    expect(loader.total.value).toBe(23968892)
  })
  it('翻页与修改每页条数复用已有总量，仅筛选变化时重算计数', async () => {
    const q = initialQuery()
    api.list.mockResolvedValue({ items: [], has_more: true })
    api.count.mockResolvedValueOnce({ state: 'ready', data: { total: 1200 } })
      .mockResolvedValueOnce({ state: 'ready', data: { total: 88 } })
    const loader = setup(() => ({ ...q }))
    await loader.load()
    await Promise.resolve()
    expect(loader.total.value).toBe(1200)
    expect(api.count).toHaveBeenCalledTimes(1)

    q.page = 2
    q.page_size = 50
    await loader.load()
    expect(loader.total.value).toBe(1200)
    expect(api.count).toHaveBeenCalledTimes(1)

    q.purchaser_provname = ['广东省']
    q.page = 1
    await loader.load()
    await Promise.resolve()
    expect(loader.total.value).toBe(88)
    expect(api.count).toHaveBeenCalledTimes(2)
  })
  it('旧请求后到时不覆盖新筛选结果，末页直接回填精确总量并停止后台计数', async () => {
    let resolve!: (value: TenderPage) => void
    api.list.mockImplementationOnce(() => new Promise<TenderPage>(done => { resolve = done }))
      .mockResolvedValueOnce({ items: [], has_more: false })
    api.count.mockResolvedValue({ state: 'pending', data: null })
    const loader = setup()
    const old = loader.load()
    await loader.load()
    resolve({ items: [], has_more: true, page: 1, page_size: 20 })
    await old
    expect(loader.hasMore.value).toBe(false)
    expect(loader.total.value).toBe(0)
    expect(api.count).toHaveBeenCalledTimes(1)
  })
  it('计数失败或超过最大轮询次数后停止重试并保留列表', async () => {
    vi.useFakeTimers()
    api.list.mockResolvedValue({ items: [], has_more: true })
    api.count.mockResolvedValue({ state: 'pending', data: null })
    const loader = setup()
    await loader.load()
    for (let i = 1; i < MAX_COUNT_POLLS; i++) {
      await vi.advanceTimersByTimeAsync(3000)
    }
    expect(api.count).toHaveBeenCalledTimes(MAX_COUNT_POLLS)
    expect(loader.countMessage.value).toContain('超时')
    await vi.advanceTimersByTimeAsync(9000)
    expect(api.count).toHaveBeenCalledTimes(MAX_COUNT_POLLS)

    // 计数报错且手动刷新可重新触发
    api.count.mockResolvedValueOnce({ state: 'error', data: null, message: '统计超时' })
    await loader.load()
    await Promise.resolve()
    expect(loader.hasMore.value).toBe(true)
    expect(loader.countMessage.value).toContain('列表仍可浏览')
    expect(loader.loadError.value).toBe('')
  })
  it('计数接口异常和默认 project_status 不计入 resultFiltered', async () => {
    const q = { ...initialQuery(), public_date_from: '', public_date_to: '' }
    api.list.mockResolvedValue({ items: [], has_more: true })
    api.count.mockRejectedValueOnce(new Error('network'))
    const loader = setup(() => ({ ...q }))
    await loader.load()
    await Promise.resolve()
    expect(loader.resultFiltered.value).toBe(false)
    expect(loader.countMessage.value).toBeTruthy()

    q.project_status = '0'
    api.count.mockResolvedValueOnce({ state: 'ready', data: { total: 5 } })
    await loader.load()
    expect(loader.resultFiltered.value).toBe(true)
  })
})
