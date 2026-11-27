import { reactive, watch } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'

const PAGE_SIZES = [10, 20, 50, 100]

export type ThinktankDictQuery = {
  keyword: string[]
  page: number
  page_size: number
}

export function querySignature(source: Record<string, unknown>): string {
  return JSON.stringify(source, Object.keys(source).sort())
}

function parsePositiveInt(raw: unknown, fallback: number, allowed?: number[]): number {
  const value = Number(Array.isArray(raw) ? raw[0] : raw)
  if (!Number.isSafeInteger(value) || value <= 0) return fallback
  if (allowed && !allowed.includes(value)) return fallback
  return value
}

function parseKeywords(raw: unknown): string[] {
  if (raw === undefined || raw === null) return []
  const list = Array.isArray(raw) ? raw : [raw]
  return list.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
}

/**
 * 智库码表复用页的查询状态与地址栏同步。
 * 与通用 useListQuery 的区别在于：6 张码表复用同一组件实例，切路由时需更新当前 path 并重置筛选。
 */
export function useThinktankDictQuery(reload: () => Promise<void>) {
  const route = useRoute()
  const router = useRouter()
  const query = reactive<ThinktankDictQuery>({ keyword: [], page: 1, page_size: 20 })
  const applied = reactive<ThinktankDictQuery>({ keyword: [], page: 1, page_size: 20 })

  let currentPath = route.path
  let committing = false
  let committedSig = ''

  function restoreFromRoute(): void {
    const raw = route.query ?? {}
    query.keyword = parseKeywords(raw.keyword)
    query.page = parsePositiveInt(raw.page, 1)
    query.page_size = parsePositiveInt(raw.page_size, 20, PAGE_SIZES)
  }

  function captureApplied(): void {
    applied.keyword = [...query.keyword]
    applied.page = query.page
    applied.page_size = query.page_size
  }

  function requested(): ThinktankDictQuery {
    return {
      keyword: [...applied.keyword],
      page: query.page,
      page_size: query.page_size,
    }
  }

  async function commitPage(): Promise<void> {
    applied.page = query.page
    applied.page_size = query.page_size
    if (!router?.replace || route.path !== currentPath) return
    const next: LocationQueryRaw = { ...route.query }
    delete next.keyword
    delete next.page
    delete next.page_size
    if (applied.keyword.length) next.keyword = [...applied.keyword]
    if (applied.page !== 1) next.page = String(applied.page)
    if (applied.page_size !== 20) next.page_size = String(applied.page_size)
    committing = true
    try {
      if (querySignature(route.query ?? {}) !== querySignature(next)) {
        await router.replace({ path: currentPath, query: next })
      }
      committedSig = querySignature(route.query ?? {})
    } finally {
      committing = false
    }
  }

  function search(): void {
    query.page = 1
    captureApplied()
    void reload()
  }

  function resetFilters(): void {
    query.keyword = []
    search()
  }

  /** 切换 slug 时调用：跨路由切换时按新路由参数恢复，同路由仅改 prop 时清空筛选。 */
  function syncForSlugChange(): void {
    const pathChanged = route.path !== currentPath
    currentPath = route.path
    if (pathChanged) {
      restoreFromRoute()
    } else {
      query.keyword = []
      query.page = 1
    }
    captureApplied()
    committedSig = querySignature(route.query ?? {})
  }

  restoreFromRoute()
  captureApplied()
  committedSig = querySignature(route.query ?? {})

  watch(
    () => route.query,
    () => {
      const sig = querySignature(route.query ?? {})
      if (committing || route.path !== currentPath || sig === committedSig) return
      committedSig = sig
      restoreFromRoute()
      captureApplied()
      void reload()
    },
  )

  return { query, applied, requested, commitPage, search, resetFilters, syncForSlugChange }
}
