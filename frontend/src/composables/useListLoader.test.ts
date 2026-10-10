import { describe, expect, it, vi } from 'vitest'

import { hasActiveFilters, useListLoader, type PageResult } from './useListLoader'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

type Params = Record<string, unknown>

function setup(fetch: (params: Params) => Promise<PageResult<string>>, params: Params = { page: 1, page_size: 20 }) {
  const commitPage = vi.fn()
  const loader = useListLoader<string, Params>({ requested: () => params, commitPage, fetch, errorText: '加载失败' })
  return { loader, commitPage }
}

describe('hasActiveFilters', () => {
  it('只看分页以外的条件，空字符串和空数组不算', () => {
    expect(hasActiveFilters({ page: 2, page_size: 50 })).toBe(false)
    expect(hasActiveFilters({ page: 1, name: '', tags: [] })).toBe(false)
    expect(hasActiveFilters({ page: 1, tags: ['政策'] })).toBe(true)
    expect(hasActiveFilters({ page: 1, name: '财政部' })).toBe(true)
  })
})

describe('useListLoader', () => {
  it('加载成功后写入数据、总数，并记录结果是否经过筛选', async () => {
    const { loader, commitPage } = setup(() => Promise.resolve({ items: ['a', 'b'], total: 2 }), { page: 1, name: 'x' })
    await loader.load()
    expect(loader.items.value).toEqual(['a', 'b'])
    expect(loader.total.value).toBe(2)
    expect(loader.resultFiltered.value).toBe(true)
    expect(loader.loading.value).toBe(false)
    expect(commitPage).toHaveBeenCalledOnce()
  })

  it('先发后到的旧响应不覆盖新结果，加载状态跟随最后一次请求', async () => {
    const first = deferred<PageResult<string>>()
    const second = deferred<PageResult<string>>()
    const fetch = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { loader } = setup(fetch)
    const older = loader.load()
    const newer = loader.load()
    second.resolve({ items: ['新'], total: 1 })
    await newer
    first.resolve({ items: ['旧'], total: 9 })
    await older
    expect(loader.items.value).toEqual(['新'])
    expect(loader.total.value).toBe(1)
    expect(loader.loading.value).toBe(false)
  })

  it('失败时给出提示，旧请求的失败不覆盖新结果', async () => {
    const first = deferred<PageResult<string>>()
    const fetch = vi.fn().mockReturnValueOnce(first.promise).mockRejectedValueOnce(new Error(''))
    const { loader } = setup(fetch)
    const older = loader.load()
    await loader.load()
    expect(loader.loadError.value).toBe('加载失败')
    first.reject(new Error('旧请求失败'))
    await older
    expect(loader.loadError.value).toBe('加载失败')
  })
})
