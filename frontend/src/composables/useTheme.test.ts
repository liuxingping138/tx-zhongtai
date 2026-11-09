import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { initTheme, useTheme } from './useTheme'

describe('useTheme', () => {
  const store = new Map<string, string>()
  const classList = new Set<string>()
  const attrs = new Map<string, string>()

  beforeEach(() => {
    store.clear()
    classList.clear()
    attrs.clear()

    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => store.set(k, v),
      removeItem: (k: string) => store.delete(k),
      clear: () => store.clear(),
    })

    vi.stubGlobal('document', {
      documentElement: {
        classList: {
          add: (c: string) => classList.add(c),
          remove: (c: string) => classList.delete(c),
          contains: (c: string) => classList.has(c),
        },
        setAttribute: (k: string, v: string) => attrs.set(k, v),
        removeAttribute: (k: string) => attrs.delete(k),
        getAttribute: (k: string) => attrs.get(k) ?? null,
      },
    })

    vi.stubGlobal('window', {
      matchMedia: vi.fn(() => ({
        matches: false,
        addEventListener: vi.fn(),
      })),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('默认为 auto 且正确读写 localStorage 与切换主题', () => {
    initTheme()
    const { theme, isDark, setTheme, toggleTheme } = useTheme()
    expect(theme.value).toBe('auto')

    setTheme('dark')
    expect(theme.value).toBe('dark')
    expect(isDark.value).toBe(true)
    expect(classList.has('dark')).toBe(true)
    expect(attrs.get('data-theme')).toBe('dark')
    expect(store.get('tx-theme')).toBe('dark')

    toggleTheme()
    expect(theme.value).toBe('light')
    expect(isDark.value).toBe(false)
    expect(classList.has('dark')).toBe(false)
    expect(attrs.get('data-theme')).toBe('light')
  })
})
