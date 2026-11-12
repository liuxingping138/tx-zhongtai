import { onBeforeUnmount, ref } from 'vue'
import { errorMessage } from '@/api/errors'
import { getTenderCount, listTenderRecords, type TenderKind, type TenderRecord } from '@/api/tender'
import { hasActiveFilters } from '@/composables/useListLoader'
import type { TenderQuery } from './fields'

interface QueryState { requested: () => TenderQuery; commitPage: () => Promise<void> }

/** 列表先返回一页；慢速精确计数独立轮询，旧筛选的计数不能覆盖当前页。 */
export function useTenderList(kind: TenderKind, query: QueryState) {
  const items = ref<TenderRecord[]>([])
  const total = ref<number | null>(null)
  const hasMore = ref(false)
  const loading = ref(false)
  const loadError = ref('')
  const countMessage = ref('正在统计总量…')
  const resultFiltered = ref(false)
  let sequence = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  onBeforeUnmount(() => { sequence++; clearTimeout(timer) })

  async function count(params: TenderQuery, current: number): Promise<void> {
    try {
      const result = await getTenderCount(kind, params)
      if (current !== sequence) return
      if (result.state === 'ready' && result.data) total.value = result.data.total
      else if (result.state === 'error') countMessage.value = `${result.message}（列表仍可浏览）`
      else timer = setTimeout(() => { void count(params, current) }, 3000)
    } catch (cause) {
      if (current === sequence) countMessage.value = errorMessage(cause, '总量暂不可用，列表仍可浏览')
    }
  }
  async function load(): Promise<void> {
    const current = ++sequence
    clearTimeout(timer)
    const params = query.requested()
    void query.commitPage()
    loading.value = true
    total.value = null
    loadError.value = ''
    countMessage.value = '正在统计总量…'
    try {
      const result = await listTenderRecords(kind, params)
      if (current !== sequence) return
      items.value = result.items
      hasMore.value = result.has_more
      resultFiltered.value = hasActiveFilters(params)
      if (!result.has_more && (params.page === 1 || result.items.length > 0)) {
        total.value = (params.page - 1) * params.page_size + result.items.length
      } else void count(params, current)
    } catch (cause) {
      if (current === sequence) loadError.value = errorMessage(cause, '招中标数据加载失败')
    } finally { if (current === sequence) loading.value = false }
  }
  return { items, total, hasMore, loading, loadError, countMessage, resultFiltered, load }
}
