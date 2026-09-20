import { reactive, watch } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'

type Value = string | number | string[] | null
/** Commit on a query request, not each keystroke. No credentials or record data are stored. */
export function useListQuery<T extends Record<string, Value>>(query: T, reload: () => Promise<void>, privateKeys: string[] = []) {
  const route = useRoute()
  const router = useRouter()
  const path = route.path
  const defaults = JSON.parse(JSON.stringify(query)) as T
  let committed = ''
  function restore() {
    const next: Record<string, Value> = { ...defaults }
    for (const key of Object.keys(defaults)) {
      if (privateKeys.includes(key)) continue
      const raw = route.query[key]
      if (raw === undefined) continue
      if (typeof defaults[key] === 'number') {
        const number = Number(raw)
        if (Number.isSafeInteger(number) && number > 0 && (key !== 'page_size' || [10, 20, 50, 100].includes(number))) next[key] = number
      } else if (Array.isArray(defaults[key]) || defaults[key] === null) {
        next[key] = (Array.isArray(raw) ? raw : [raw]).filter((v): v is string => typeof v === 'string')
      } else if (typeof raw === 'string') next[key] = raw
    }
    for (const key of privateKeys) next[key] = query[key] ?? defaults[key] ?? ''
    Object.assign(query, next)
  }
  function signature(source: Record<string, unknown> = route.query as Record<string, unknown>) {
    return JSON.stringify(source, Object.keys(source).sort())
  }
  const applied = reactive(JSON.parse(JSON.stringify(query)) as T)
  function captureApplied() {
    const next = JSON.parse(JSON.stringify(query)) as T
    for (const key of Object.keys(applied)) {
      if (!(key in next)) delete (applied as Record<string, unknown>)[key]
    }
    Object.assign(applied, next)
  }
  restore()
  captureApplied()
  committed = signature()
  let committing = false
  async function commit() {
    if (route.path !== path) return
    const next: LocationQueryRaw = { ...route.query }
    for (const [key, value] of Object.entries(query)) {
      delete next[key]
      if (privateKeys.includes(key)) continue
      if (Array.isArray(value) ? value.length : value !== '' && value !== null && value !== defaults[key]) next[key] = Array.isArray(value) ? value : String(value)
    }
    committing = true
    try {
      if (signature() !== signature(next as Record<string, unknown>)) await router.replace({ path, query: next })
      committed = signature()
    } finally {
      committing = false
    }
  }
  watch(() => route.query, () => {
    if (committing || route.path !== path || signature() === committed) return
    committed = signature()
    restore()
    captureApplied()
    void reload()
  })
  return { commit, applied, captureApplied }
}
