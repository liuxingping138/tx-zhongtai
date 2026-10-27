import type { LocationQuery, LocationQueryRaw } from 'vue-router'

const DEFAULT_PAGE_SIZE = 20
const PAGE_SIZES = [10, 20, 50, 100]
const PAGING_KEYS = ['page', 'page_size']

/** 核对页从地址栏还原出的列表上下文：用哪些筛选、这条在结果里排第几（从 0 起），列表每页几条。 */
export interface ReviewContext {
  filters: Record<string, string[]>
  position: number | null
  pageSize: number
}

/**
 * 从列表进核对页时带上的地址参数：已生效的筛选（同字段多值照列表的写法重复）、
 * 这条在筛选结果里的位置 pos 和列表每页条数 ps，刷新、上一条下一条、返回列表都靠它们。
 */
export function reviewQuery(applied: Record<string, unknown>, position: number, pageSize: number): LocationQueryRaw {
  const query: LocationQueryRaw = {}
  for (const [key, value] of Object.entries(applied)) {
    if (PAGING_KEYS.includes(key)) continue
    const values = (Array.isArray(value) ? value : [value]).filter((item): item is string => typeof item === 'string' && item !== '')
    if (values.length) query[key] = values
  }
  query.pos = String(position)
  if (pageSize !== DEFAULT_PAGE_SIZE) query.ps = String(pageSize)
  return query
}

/** 只认列表定义过的筛选字段，地址栏里别的参数不带进查询。 */
export function parseReviewQuery(query: LocationQuery, filterKeys: readonly string[]): ReviewContext {
  const filters: Record<string, string[]> = {}
  for (const key of filterKeys) {
    const raw = query[key]
    const values = (Array.isArray(raw) ? raw : [raw]).filter((item): item is string => typeof item === 'string' && item !== '')
    if (values.length) filters[key] = values
  }
  const position = Number(query.pos)
  const pageSize = Number(query.ps)
  return {
    filters,
    position: typeof query.pos === 'string' && Number.isSafeInteger(position) && position >= 0 ? position : null,
    pageSize: PAGE_SIZES.includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE,
  }
}

/** 返回列表：带回原来的筛选，并翻到这条所在的那一页。 */
export function listQuery(context: ReviewContext): LocationQueryRaw {
  const query: LocationQueryRaw = { ...context.filters }
  if (context.position !== null) {
    const page = Math.floor(context.position / context.pageSize) + 1
    if (page > 1) query.page = String(page)
  }
  if (context.pageSize !== DEFAULT_PAGE_SIZE) query.page_size = String(context.pageSize)
  return query
}
