import { http, request } from './http'

/** 智库访问白名单（只在公司网络能用，别处要管理员按 IP 开有时效的白名单）。 */
export interface IpWhitelistItem {
  id: string
  ip_range: string
  holder: string
  reason: string
  /** 北京时间 YYYY-MM-DD HH:mm:ss */
  expires_at: string
  active: boolean
  created_by_name: string
  created_at: string
  updated_by_name: string
  updated_at: string
}

export interface NetworkDecision {
  ip: string
  allowed: boolean
  /** office 公司网络；whitelist 白名单；disabled 本环境没开限制；空串表示被拦 */
  via: 'office' | 'whitelist' | 'disabled' | ''
  expires_at: string
}

export interface IpWhitelistOverview {
  items: IpWhitelistItem[]
  office_networks: string[]
  guard_enabled: boolean
  max_days: number
  current: NetworkDecision
}

export interface IpWhitelistPayload {
  ip_range: string
  holder: string
  reason: string
  /** 带时区的 ISO 时间，或不带时区的「YYYY-MM-DD HH:mm:ss」（后端按北京时间理解） */
  expires_at: string
}

/** 被网络准入拦下时后端回的错误码（403）。 */
export const NETWORK_DENIED_CODE = 'THINKTANK_NETWORK_DENIED'

export function getIpWhitelist(): Promise<IpWhitelistOverview> {
  return request(http.get('/thinktank/ip-whitelist'))
}

export function createIpWhitelist(payload: IpWhitelistPayload): Promise<IpWhitelistItem> {
  return request(http.post('/thinktank/ip-whitelist', payload))
}

export function updateIpWhitelist(id: string, payload: IpWhitelistPayload): Promise<IpWhitelistItem> {
  return request(http.put(`/thinktank/ip-whitelist/${id}`, payload))
}

export function deleteIpWhitelist(id: string): Promise<{ id: string }> {
  return request(http.delete(`/thinktank/ip-whitelist/${id}`))
}
