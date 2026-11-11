import { http, request } from './http'
import type { AuditEventItem, FilterParam, Page } from './types'

export function listAuditEvents(params: {
  page?: number
  page_size?: number
  occurred_from?: string
  occurred_to?: string
  actor_id?: string
  actor_name?: FilterParam
  module_root?: FilterParam
  module_code?: FilterParam
  business_line?: FilterParam
  action_code?: FilterParam
  outcome?: FilterParam
}): Promise<Page<AuditEventItem>> {
  return request(http.get('/audit/events', { params }))
}

export function getAuditEvent(eventId: string): Promise<AuditEventItem> {
  return request(http.get(`/audit/events/${eventId}`))
}
