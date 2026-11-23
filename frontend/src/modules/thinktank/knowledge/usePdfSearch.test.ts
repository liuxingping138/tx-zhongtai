import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { SEARCH_DEBOUNCE_MS, usePdfSearch, type SearchHit } from './usePdfSearch'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => { resolve = res })
  return { promise, resolve }
}

function setup(pages: string[][], pageText?: (n: number) => Promise<string[]> | null) {
  const numPages = ref(pages.length)
  const jumps: SearchHit[] = []
  const fetch = vi.fn(pageText ?? ((n: number) => Promise.resolve(pages[n - 1]!)))
  const search = usePdfSearch({ numPages, pageText: fetch, onJump: hit => jumps.push(hit) })
  return { search, fetch, jumps, numPages }
}

async function settle() {
  await vi.runAllTimersAsync()
}

describe('usePdfSearch', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('没输入查找词之前一页文字都不取；打开查找条也不取', async () => {
    const { search, fetch } = setup([['政府'], ['数字']])
    search.show()
    expect(search.open.value).toBe(true)
    await settle()
    expect(fetch).not.toHaveBeenCalled()
    search.setQuery('   ')
    await settle()
    expect(fetch).not.toHaveBeenCalled()
    expect(search.label.value).toBe('无匹配')
  })

  it('停顿后逐页取文字、找到第一处就跳过去；取过的页缓存起来', async () => {
    const { search, fetch, jumps } = setup([['数字'], ['数字政', '府'], ['政府政府']])
    search.show()
    search.setQuery('政府')
    await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS - 1)
    expect(fetch).not.toHaveBeenCalled()
    await settle()
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(search.hits.value.map(hit => [hit.page, hit.indexInPage])).toEqual([[2, 0], [3, 0], [3, 1]])
    expect(jumps).toEqual([search.hits.value[0]])
    expect(search.label.value).toBe('第 1 / 3 处')
    expect(search.pageSelection(2)).toBe(0)
    expect(search.pageSelection(3)).toBe(-1)

    search.setQuery('数字')
    await settle()
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(search.hits.value).toHaveLength(2)
  })

  it('Enter 同一个词跳下一处、Shift+Enter 上一处，首尾循环', async () => {
    const { search, jumps } = setup([['政府'], ['政府政府']])
    search.setQuery('政府')
    await settle()
    search.submit()
    expect(search.current.value).toBe(1)
    search.step(1)
    search.step(1)
    expect(search.current.value).toBe(0)
    search.submit(true)
    expect(search.current.value).toBe(2)
    expect(search.pageSelection(2)).toBe(1)
    expect(jumps).toHaveLength(5)
  })

  it('还在停顿中按 Enter 立刻找；没有匹配时上下一处不动', async () => {
    const { search, fetch, jumps } = setup([['数字']])
    search.setQuery('政府')
    search.submit()
    await Promise.resolve()
    expect(fetch).toHaveBeenCalledTimes(1)
    await settle()
    expect(fetch).toHaveBeenCalledTimes(1)
    search.step(1)
    expect(jumps).toEqual([])
    expect(search.current.value).toBe(-1)
  })

  it('换查找词立即作废上一轮：后面的页不再去取', async () => {
    const slow = deferred<string[]>()
    const { search, fetch } = setup([['a'], ['b'], ['c']], n => (n === 1 ? slow.promise : Promise.resolve(['政府'])))
    search.setQuery('政府')
    await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS)
    expect(search.scanning.value).toBe(true)
    expect(search.label.value).toBe('正在查找…')
    search.setQuery('数字')
    slow.resolve(['政府'])
    await Promise.resolve()
    await Promise.resolve()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(search.hits.value).toEqual([])
  })

  it('关掉查找：作废这一轮、清掉结果；没开时返回 false', async () => {
    const slow = deferred<string[]>()
    const { search, fetch } = setup([['a'], ['b']], () => slow.promise)
    expect(search.close()).toBe(false)
    search.show()
    search.setQuery('政府')
    await vi.advanceTimersByTimeAsync(SEARCH_DEBOUNCE_MS)
    expect(search.close()).toBe(true)
    slow.resolve(['政府'])
    await settle()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(search.open.value).toBe(false)
    expect(search.query.value).toBe('')
    expect(search.hits.value).toEqual([])
    expect(search.scanning.value).toBe(false)
  })

  it('换文档：清掉缓存，查找条开着就按原词重找；取不到的页当没有匹配', async () => {
    const pages = [['政府'], ['政府']]
    let fail = false
    const { search, fetch } = setup(pages, (n) => {
      if (fail && n === 2) return Promise.reject(new Error('net'))
      return Promise.resolve(pages[n - 1]!)
    })
    search.show()
    search.setQuery('政府')
    await settle()
    expect(search.hits.value).toHaveLength(2)
    fail = true
    search.reset()
    await settle()
    expect(fetch).toHaveBeenCalledTimes(4)
    expect(search.hits.value.map(hit => hit.page)).toEqual([1])

    search.close()
    search.reset()
    await settle()
    expect(fetch).toHaveBeenCalledTimes(4)
  })

  it('文档已关掉（取文字返回 null）时不缓存、没有匹配', async () => {
    const { search } = setup([['政府']], () => null)
    search.setQuery('政府')
    await settle()
    expect(search.hits.value).toEqual([])
    expect(search.selected.value).toBeNull()
  })
})
