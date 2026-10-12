import { describe, expect, it, vi } from 'vitest'

import { clearReloadMark, isChunkLoadError, reloadForNewVersion } from './chunkReload'

function memoryStorage() {
  const data = new Map<string, string>()
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value) },
    removeItem: (key: string) => { data.delete(key) },
  }
}

describe('发布后旧分包失效时自动刷新', () => {
  it('认得各浏览器的分包加载失败，其他错误不管', () => {
    expect(isChunkLoadError(new TypeError('Failed to fetch dynamically imported module: https://x/assets/A-1.js'))).toBe(true)
    expect(isChunkLoadError(new TypeError('Importing a module script failed.'))).toBe(true)
    expect(isChunkLoadError(new Error('Unable to preload CSS for /assets/B.css'))).toBe(true)
    expect(isChunkLoadError(new Error('Network Error'))).toBe(false)
    expect(isChunkLoadError('Failed to fetch dynamically imported module')).toBe(false)
  })

  it('同一目标只刷新一次，避免服务真挂时无限刷新', () => {
    const storage = memoryStorage()
    const assign = vi.fn()
    expect(reloadForNewVersion('/policy/crawler-monitoring-v2', storage, assign)).toBe(true)
    expect(reloadForNewVersion('/policy/crawler-monitoring-v2', storage, assign)).toBe(false)
    expect(assign).toHaveBeenCalledTimes(1)
    expect(assign).toHaveBeenCalledWith('/policy/crawler-monitoring-v2')
  })

  it('成功进入页面后清掉标记，下次发布还能再刷新', () => {
    const storage = memoryStorage()
    const assign = vi.fn()
    reloadForNewVersion('/a', storage, assign)
    clearReloadMark(storage)
    expect(reloadForNewVersion('/a', storage, assign)).toBe(true)
  })
})
