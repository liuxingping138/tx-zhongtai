import { onBeforeUnmount, ref } from 'vue'
import { errorMessage } from '@/api/errors'
import { getTenderCount, listTenderRecords, type TenderKind, type TenderRecord } from '@/api/tender'
import { hasActiveFilters } from '@/composables/useListLoader'
import type { TenderQuery } from './fields'

interface QueryState { requested: () => TenderQuery; commitPage: () => Promise<void> }

export const MAX_COUNT_POLLS = 40

function filterSignature(params: TenderQuery): string {
  const keys = Object.keys(params).filter(key => key !== 'page' && key !== 'page_size').sort()
  return JSON.stringify(params, keys)
}

function hasTenderFilters(params: TenderQuery): boolean {
  const { project_status: status, ...rest } = params
  return (status !== '' && status !== '1' && status !== 'all') || hasActiveFilters(rest)
}

/** 列表先返回一页；慢速精确计数与列表并行拉取，翻页复用同一筛选的总量，且限制最大轮询次数避免无限重试。 */
export function useTenderList(kind: TenderKind, query: QueryState) {
  const items = ref<TenderRecord[]>([])
  const total = ref<number | null>(null)
  const hasMore = ref(false)
  const loading = ref(false)
  const loadError = ref('')
  const countMessage = ref('正在统计总量…')
  const resultFiltered = ref(false)
  let sequence = 0
  let countSeq = 0
  let lastFilterSig = ''
  let countInFlight = false
  let timer: ReturnType<typeof setTimeout> | undefined
  onBeforeUnmount(() => { sequence++; countSeq++; clearTimeout(timer) })

  async function count(params: TenderQuery, currentCount: number, attempt = 0): Promise<void> {
    countInFlight = true
    try {
      const result = await getTenderCount(kind, params)
      if (currentCount !== countSeq) return
      if (result.state === 'ready' && result.data) {
        total.value = result.data.total
        countInFlight = false
      } else if (result.state === 'error') {
        countMessage.value = `${result.message}（列表仍可浏览）`
        countInFlight = false
      } else if (attempt + 1 >= MAX_COUNT_POLLS) {
        countMessage.value = '精确总量统计超时，请稍后刷新（列表仍可浏览）'
        countInFlight = false
      } else {
        timer = setTimeout(() => { void count(params, currentCount, attempt + 1) }, 3000)
      }
    } catch (cause) {
      if (currentCount === countSeq) {
        countMessage.value = errorMessage(cause, '总量暂不可用，列表仍可浏览')
        countInFlight = false
      }
    }
  }

  function syncBackgroundCount(params: TenderQuery): void {
    const sig = filterSignature(params)
    const filterChanged = sig !== lastFilterSig
    if (!filterChanged && (total.value !== null || countInFlight)) return
    lastFilterSig = sig
    clearTimeout(timer)
    const currentCount = ++countSeq
    if (filterChanged) total.value = null
    countMessage.value = '正在统计总量…'
    void count(params, currentCount)
  }

  async function load(): Promise<void> {
    const current = ++sequence
    const params = query.requested()
    void query.commitPage()
    loading.value = true
    loadError.value = ''
    syncBackgroundCount(params)

    try {
      const result = await listTenderRecords(kind, params)
      if (current !== sequence) return
      items.value = result.items
      hasMore.value = result.has_more
      resultFiltered.value = hasTenderFilters(params)
      if (!result.has_more && (params.page === 1 || result.items.length > 0)) {
        clearTimeout(timer)
        countSeq++
        countInFlight = false
        total.value = (params.page - 1) * params.page_size + result.items.length
      }
    } catch (cause) {
      if (current === sequence) loadError.value = errorMessage(cause, '招中标数据加载失败')
    } finally { if (current === sequence) loading.value = false }
  }
  return { items, total, hasMore, loading, loadError, countMessage, resultFiltered, load }
}
