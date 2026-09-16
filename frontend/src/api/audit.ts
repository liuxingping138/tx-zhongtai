import { http, request } from './http'
import type { AuditEventItem, Page } from './types'

export function listAuditEvents(params: {
  page?: number
  page_size?: number
  occurred_from?: string
  occurred_to?: string
  actor_id?: string
  actor_name?: string
  module_code?: string
  action_code?: string
  outcome?: string
}): Promise<Page<AuditEventItem>> {
  return request(http.get('/audit/events', { params }))
}

export function getAuditEvent(eventId: string): Promise<AuditEventItem> {
  return request(http.get(`/audit/events/${eventId}`))
}
