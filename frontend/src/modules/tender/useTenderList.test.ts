import { afterEach, describe, expect, it, vi } from 'vitest'
import { initialQuery } from './fields'
import { useTenderList } from './useTenderList'
import type { TenderPage } from '@/api/tender'

const api = vi.hoisted(() => ({ list: vi.fn(), count: vi.fn() }))
vi.mock('@/api/tender', () => ({ listTenderRecords: api.list, getTenderCount: api.count }))
vi.mock('vue', async importOriginal => ({ ...await importOriginal<typeof import('vue')>(), onBeforeUnmount: vi.fn() }))
const setup = () => useTenderList('winbid', { requested: initialQuery, commitPage: () => Promise.resolve() })
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers() })

describe('招中标列表与后台计数', () => {
  it('列表先返回，计数完成后单独补充', async () => {
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
  it('旧请求后到时不覆盖新筛选结果', async () => {
    let resolve!: (value: TenderPage) => void
    api.list.mockImplementationOnce(() => new Promise<TenderPage>(done => { resolve = done }))
      .mockResolvedValueOnce({ items: [], has_more: false })
    const loader = setup()
    const old = loader.load()
    await loader.load()
    resolve({ items: [], has_more: true, page: 1, page_size: 20 })
    await old
    expect(loader.hasMore.value).toBe(false)
    expect(loader.total.value).toBe(0)
    expect(api.count).not.toHaveBeenCalled()
  })
  it('计数失败仍保留列表及下一页', async () => {
    api.list.mockResolvedValue({ items: [], has_more: true })
    api.count.mockResolvedValue({ state: 'error', data: null, message: '统计超时' })
    const loader = setup()
    await loader.load()
    await Promise.resolve()
    expect(loader.hasMore.value).toBe(true)
    expect(loader.countMessage.value).toContain('列表仍可浏览')
    expect(loader.loadError.value).toBe('')
  })
})
