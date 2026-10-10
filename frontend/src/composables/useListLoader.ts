import { ref, type Ref } from 'vue'

import { errorMessage } from '@/api/errors'

export interface PageResult<T> {
  items: T[]
  total: number
}

interface ListLoaderOptions<T, P> {
  /** 本次要查的条件（已生效筛选 + 当前页码），通常是 listQuery.requested。 */
  requested: () => P
  /** 把页码写回地址栏，通常是 listQuery.commitPage。 */
  commitPage: () => unknown
  fetch: (params: P) => Promise<PageResult<T>>
  /** 失败时的兜底提示，如「加载信源失败」。 */
  errorText: string
}

const PAGING_KEYS = new Set(['page', 'page_size'])

/** 除分页外是否有生效的筛选条件：决定空结果显示「没有匹配」还是「暂无数据」。 */
export function hasActiveFilters(params: Record<string, unknown>): boolean {
  return Object.entries(params).some(([key, value]) =>
    !PAGING_KEYS.has(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
}

/**
 * 列表加载：维护数据、总数、加载中、错误和「结果是否经过筛选」。
 * 连续触发时只采用最后一次请求的结果，先发后到的旧响应不会覆盖新结果。
 */
export function useListLoader<T, P extends Record<string, unknown>>(options: ListLoaderOptions<T, P>) {
  const items = ref([]) as Ref<T[]>
  const total = ref(0)
  const loading = ref(false)
  const loadError = ref('')
  const resultFiltered = ref(false)
  let sequence = 0

  async function load(): Promise<void> {
    const params = options.requested()
    void options.commitPage()
    const current = ++sequence
    loading.value = true
    loadError.value = ''
    const filtered = hasActiveFilters(params)
    try {
      const page = await options.fetch(params)
      if (current !== sequence) return
      items.value = page.items
      total.value = page.total
      resultFiltered.value = filtered
    } catch (error) {
      if (current !== sequence) return
      loadError.value = errorMessage(error, options.errorText)
    } finally {
      if (current === sequence) loading.value = false
    }
  }

  return { items, total, loading, loadError, resultFiltered, load }
}
