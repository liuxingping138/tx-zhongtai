/** 操作日志的筛选条件和请求参数。页面上的「业务模块」换算成模块编码第一段（module_root）发给后端。 */
import { directoryRoots } from '@/utils/auditLabels'
import { toBeijingIso } from '@/utils/time'

export interface AuditQuery {
  actor_name: string[]
  directory: string[]
  business_line: string[]
  module_code: string[]
  action_code: string[]
  outcome: string[]
  range: string[] | null
  page: number
  page_size: number
}

export function emptyAuditQuery(): AuditQuery {
  return { actor_name: [], directory: [], business_line: [], module_code: [], action_code: [], outcome: [], range: [], page: 1, page_size: 20 }
}

export function hasFilters(params: AuditQuery): boolean {
  return Object.entries(params).some(([key, value]) =>
    !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
}

const listOrNone = (values: string[] | undefined) => (values?.length ? values : undefined)

export function toRequestParams(params: AuditQuery) {
  return {
    page: params.page,
    page_size: params.page_size,
    actor_name: listOrNone(params.actor_name),
    module_root: listOrNone(directoryRoots(params.directory ?? [])),
    business_line: listOrNone(params.business_line),
    module_code: listOrNone(params.module_code),
    action_code: listOrNone(params.action_code),
    outcome: listOrNone(params.outcome),
    occurred_from: toBeijingIso(params.range?.[0]) || undefined,
    occurred_to: toBeijingIso(params.range?.[1]) || undefined,
  }
}
