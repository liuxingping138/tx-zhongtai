import { reactive, watch } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'

type Value = string | number | string[] | null
const PAGING_KEYS = ['page', 'page_size']
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
  function signature(source: Record<string, unknown> = route.query) {
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
  function requested(): T {
    const next = JSON.parse(JSON.stringify(applied)) as T
    const live = query as Record<string, Value>
    const record = next as Record<string, Value>
    for (const key of PAGING_KEYS) {
      const value = live[key]
      if (value !== undefined) record[key] = value
    }
    return next
  }
  async function writeUrl(source: T) {
    if (route.path !== path) return
    const next: LocationQueryRaw = { ...route.query }
    for (const [key, value] of Object.entries(source)) {
      delete next[key]
      if (privateKeys.includes(key)) continue
      if (Array.isArray(value) ? value.length : value !== '' && value !== null && value !== defaults[key]) {
        next[key] = Array.isArray(value) ? value : String(value)
      }
    }
    committing = true
    try {
      if (signature() !== signature(next)) await router.replace({ path, query: next })
      committed = signature()
    } finally {
      committing = false
    }
  }
  /** 显式把当前草稿写入地址栏。列表刷新不要用它，否则没点查询的条件会生效。 */
  async function commit() {
    await writeUrl(query)
  }
  /**
   * 翻页、重试、保存后刷新：地址栏和请求只用已生效的筛选，加上当前页码。
   * 输入框里的草稿留在表单上，等用户点查询。
   */
  async function commitPage() {
    const source = requested()
    const live = query as Record<string, Value>
    const stored = applied as Record<string, Value>
    for (const key of PAGING_KEYS) {
      const value = live[key]
      if (value !== undefined) stored[key] = value
    }
    await writeUrl(source)
  }
  /** 图例、状态卡片：只改已生效条件里的一列，其它未查询的草稿不参与。 */
  function replaceApplied(key: string, value: Value) {
    const stored = applied as Record<string, Value>
    const live = query as Record<string, Value>
    stored[key] = JSON.parse(JSON.stringify(value)) as Value
    live[key] = JSON.parse(JSON.stringify(value)) as Value
    if ('page' in live) live.page = 1
    if ('page' in stored) stored.page = 1
  }
  watch(() => route.query, () => {
    if (committing || route.path !== path || signature() === committed) return
    committed = signature()
    restore()
    captureApplied()
    void reload()
  })
  return { commit, commitPage, requested, applied, captureApplied, replaceApplied }
}

/** 把筛选值（多选数组或旧的单值）统一成去空、去重的字符串数组。 */
export function filterList(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : [value]
  return [...new Set(raw.filter((item): item is string => typeof item === 'string' && item.trim() !== '').map(item => item.trim()))]
}

/** 多选里有这个值就去掉，没有就加上。状态卡片、图例这类「点一下筛选、再点取消」的入口用它。 */
export function toggleValue(values: unknown, value: string): string[] {
  const current = filterList(values)
  return current.includes(value) ? current.filter(item => item !== value) : [...current, value]
}

/**
 * 取「已生效」的筛选条件用于导出。
 *
 * 用 applied 而不是 query：query 是用户正在输入、还没点查询的值，
 * 用它导出会导出屏幕上没看到的结果。去掉分页参数，导出本来就不分页。
 */
export function filtersForExport(applied: Record<string, unknown>): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = {}
  for (const [key, value] of Object.entries(applied)) {
    if (PAGING_KEYS.includes(key)) continue
    if (typeof value === 'string' && value !== '') out[key] = value
    else if (typeof value === 'number') out[key] = String(value)
    else if (Array.isArray(value)) {
      const values = value.filter((item): item is string => typeof item === 'string' && item !== '')
      if (values.length) out[key] = values
    }
  }
  return out
}
