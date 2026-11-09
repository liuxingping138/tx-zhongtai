import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { initDensity, useTableDensity } from './useTableDensity'

describe('useTableDensity', () => {
  const store = new Map<string, string>()
  const attrs = new Map<string, string>()

  beforeEach(() => {
    store.clear()
    attrs.clear()

    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => store.set(k, v),
      removeItem: (k: string) => store.delete(k),
      clear: () => store.clear(),
    })

    vi.stubGlobal('document', {
      documentElement: {
        setAttribute: (k: string, v: string) => attrs.set(k, v),
        removeAttribute: (k: string) => attrs.delete(k),
        getAttribute: (k: string) => attrs.get(k) ?? null,
      },
    })

    vi.stubGlobal('window', {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('默认为 comfortable 且正确切换至 compact', () => {
    initDensity()
    const { density, isCompact, setDensity, toggleDensity } = useTableDensity()
    expect(density.value).toBe('comfortable')
    expect(isCompact.value).toBe(false)
    expect(attrs.get('data-density')).toBe('comfortable')

    setDensity('compact')
    expect(density.value).toBe('compact')
    expect(isCompact.value).toBe(true)
    expect(attrs.get('data-density')).toBe('compact')
    expect(store.get('tx-table-density')).toBe('compact')

    toggleDensity()
    expect(density.value).toBe('comfortable')
    expect(isCompact.value).toBe(false)
    expect(attrs.get('data-density')).toBe('comfortable')
  })
})
