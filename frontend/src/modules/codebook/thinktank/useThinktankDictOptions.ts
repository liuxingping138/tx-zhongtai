import { reactive, ref, type Ref } from 'vue'

import {
  fetchFilterOptions,
  searchFilterOptions,
  type FilterOptionSet,
  type FilterOptionsPayload,
} from '@/api/filterOptions'
import type { FilterSelectBinding } from '@/composables/useFilterOptions'

const EMPTY: FilterOptionSet = { items: [], truncated: false }

function toOptionSet(raw: unknown): FilterOptionSet | null {
  if (Array.isArray(raw)) {
    return { items: raw.filter((v): v is string => typeof v === 'string'), truncated: false }
  }
  if (raw && typeof raw === 'object' && 'items' in raw) {
    const candidate = raw as { items?: unknown; truncated?: unknown }
    if (Array.isArray(candidate.items)) {
      return {
        items: candidate.items.filter((v): v is string => typeof v === 'string'),
        truncated: Boolean(candidate.truncated),
      }
    }
  }
  return null
}

/** 兼容标准 `{ options: { name: { items, truncated } } }` 及精简 `{ name: string[] }` 两种返回形态。 */
export function normalizeFilterOptions(payload: unknown): Record<string, FilterOptionSet> {
  if (!payload || typeof payload !== 'object') return {}
  const record = payload as Record<string, unknown>
  const source =
    record.options && typeof record.options === 'object' && !Array.isArray(record.options)
      ? (record.options as Record<string, unknown>)
      : record
  const out: Record<string, FilterOptionSet> = {}
  for (const [key, value] of Object.entries(source)) {
    const parsed = toOptionSet(value)
    if (parsed) out[key] = parsed
  }
  return out
}

/**
 * 响应路径切换的筛选项加载器。
 * 6 张智库码表复用同一组件实例，路径随 slug 动态切换；每次切换清空旧候选并按序号丢弃过时响应。
 */
export function useThinktankDictOptions(path: Ref<string>) {
  const sets = reactive<Record<string, FilterOptionSet>>({})
  const loaded = ref(false)
  let sequence = 0

  function clearSets(): void {
    for (const key of Object.keys(sets)) delete sets[key]
  }

  function reset(): void {
    sequence += 1
    clearSets()
    loaded.value = false
  }

  async function load(): Promise<void> {
    const targetPath = path.value
    const current = ++sequence
    try {
      const payload: FilterOptionsPayload = await fetchFilterOptions(targetPath)
      if (current !== sequence) return
      clearSets()
      Object.assign(sets, normalizeFilterOptions(payload))
      loaded.value = true
    } catch {
      /* 选项取不到不影响列表本身，筛选框退化为可自由输入。 */
    }
  }

  function bind(field: string): FilterSelectBinding {
    const set = sets[field] ?? EMPTY
    if (!set.truncated) {
      return { options: set.items }
    }
    return {
      options: set.items,
      remoteSearch: async (keyword: string) => (await searchFilterOptions(path.value, field, keyword)).items,
    }
  }

  return { load, reset, bind, loaded }
}
