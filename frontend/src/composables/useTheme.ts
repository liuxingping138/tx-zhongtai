import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'auto'

const STORAGE_KEY = 'tx-theme'
const currentTheme = ref<ThemeMode>('auto')
const prefersDark = ref(false)

let mediaQueryList: MediaQueryList | null = null

function updateHtmlElement(isDarkActive: boolean) {
  if (typeof document === 'undefined') {
    return
  }
  const root = document.documentElement
  if (isDarkActive) {
    root.classList.add('dark')
    root.setAttribute('data-theme', 'dark')
  } else {
    root.classList.remove('dark')
    root.setAttribute('data-theme', 'light')
  }
}

function handleMediaChange(e: MediaQueryListEvent | MediaQueryList) {
  prefersDark.value = e.matches
  if (currentTheme.value === 'auto') {
    updateHtmlElement(prefersDark.value)
  }
}

export function initTheme() {
  if (typeof window === 'undefined') {
    return
  }
  const stored = localStorage.getItem(STORAGE_KEY) as ThemeMode | null
  if (stored === 'light' || stored === 'dark' || stored === 'auto') {
    currentTheme.value = stored
  } else {
    currentTheme.value = 'auto'
  }

  if (typeof window.matchMedia === 'function') {
    mediaQueryList = window.matchMedia('(prefers-color-scheme: dark)')
    prefersDark.value = mediaQueryList.matches
    if (typeof mediaQueryList.addEventListener === 'function') {
      mediaQueryList.addEventListener('change', handleMediaChange)
    } else if (typeof (mediaQueryList as unknown as { addListener?: (cb: typeof handleMediaChange) => void }).addListener === 'function') {
      (mediaQueryList as unknown as { addListener: (cb: typeof handleMediaChange) => void }).addListener(handleMediaChange)
    }
  }

  const isDarkActive = currentTheme.value === 'dark' || (currentTheme.value === 'auto' && prefersDark.value)
  updateHtmlElement(isDarkActive)
}

export function useTheme() {
  const isDark = computed(() => {
    if (currentTheme.value === 'dark') {
      return true
    }
    if (currentTheme.value === 'light') {
      return false
    }
    return prefersDark.value
  })

  function setTheme(mode: ThemeMode) {
    currentTheme.value = mode
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, mode)
    }
    const isDarkActive = mode === 'dark' || (mode === 'auto' && prefersDark.value)
    updateHtmlElement(isDarkActive)
  }

  function toggleTheme() {
    setTheme(isDark.value ? 'light' : 'dark')
  }

  return {
    theme: currentTheme,
    isDark,
    setTheme,
    toggleTheme,
  }
}
