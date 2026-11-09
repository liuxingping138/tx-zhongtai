import { computed, ref } from 'vue'

export type TableDensity = 'comfortable' | 'compact'

const STORAGE_KEY = 'tx-table-density'
const currentDensity = ref<TableDensity>('comfortable')

function updateDensityElement(density: TableDensity) {
  if (typeof document === 'undefined') {
    return
  }
  document.documentElement.setAttribute('data-density', density)
}

export function initDensity() {
  if (typeof window === 'undefined') {
    return
  }
  const stored = localStorage.getItem(STORAGE_KEY) as TableDensity | null
  if (stored === 'compact' || stored === 'comfortable') {
    currentDensity.value = stored
  } else {
    currentDensity.value = 'comfortable'
  }
  updateDensityElement(currentDensity.value)
}

export function useTableDensity() {
  const isCompact = computed(() => currentDensity.value === 'compact')

  function setDensity(density: TableDensity) {
    currentDensity.value = density
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, density)
    }
    updateDensityElement(density)
  }

  function toggleDensity() {
    setDensity(isCompact.value ? 'comfortable' : 'compact')
  }

  return {
    density: currentDensity,
    isCompact,
    setDensity,
    toggleDensity,
  }
}
