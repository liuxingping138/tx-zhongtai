import { http, request } from './http'
import type { AuditEventItem, FilterParam, Page } from './types'

export function listAuditEvents(params: {
  page?: number
  page_size?: number
  occurred_from?: string
  occurred_to?: string
  actor_id?: string
  actor_name?: FilterParam
  module_code?: FilterParam
  action_code?: FilterParam
  outcome?: FilterParam
}): Promise<Page<AuditEventItem>> {
  return request(http.get('/audit/events', { params }))
}

export function getAuditEvent(eventId: string): Promise<AuditEventItem> {
  return request(http.get(`/audit/events/${eventId}`))
}

/** AI 事件早先没记模板类型：按事件目标（模板ID或任务ID）回 AI 服务查，{目标ID: 类型编码}，查不到的不出现。 */
export function getAiAuditCategories(ids: string[]): Promise<{ items: Record<string, string> }> {
  return request(http.get('/ai/audit-categories', { params: { ids } }))
}
