import { http } from './http'
import { request } from './http'

/**
 * 一个筛选字段的候选值。
 *
 * `truncated` 为真表示候选值太多、只给了前一段，输入关键词时要走服务端搜索；
 * 为假表示这就是全部候选，前端本地过滤即可，不必再发请求。
 */
export interface FilterOptionSet {
  items: string[]
  truncated: boolean
}

/** 筛选项接口的响应。`city_by_province` 只有信源管理会带。 */
export interface FilterOptionsPayload {
  options: Record<string, FilterOptionSet>
  city_by_province?: Record<string, string[]>
}

export function fetchFilterOptions(path: string): Promise<FilterOptionsPayload> {
  return request(http.get(`${path}/options`))
}

export function searchFilterOptions(path: string, field: string, keyword: string): Promise<{ items: string[] }> {
  return request(http.get(`${path}/options/search`, { params: { field, q: keyword || undefined } }))
}
