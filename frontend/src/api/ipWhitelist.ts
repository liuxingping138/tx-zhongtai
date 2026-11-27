import { http, request } from './http'

/** 访问白名单（系统管理）：限定公司网络的模块（智库），别处使用要管理员给这个人按 IP 开有时效的白名单。 */
export interface WhitelistUser {
  id: string
  username: string
  display_name: string
}

export interface IpWhitelistItem {
  id: string
  user: WhitelistUser
  ip_range: string
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
  restricted_modules: string[]
  guard_enabled: boolean
  max_days: number
  current: NetworkDecision & { user: WhitelistUser }
}

export interface IpWhitelistPayload {
  user_id: string
  ip_range: string
  reason: string
  /** 带时区的 ISO 时间，或不带时区的「YYYY-MM-DD HH:mm:ss」（后端按北京时间理解） */
  expires_at: string
}

/** 被网络限制拦下时后端回的错误码（403）。 */
export const NETWORK_DENIED_CODE = 'NETWORK_DENIED'

export function getIpWhitelist(): Promise<IpWhitelistOverview> {
  return request(http.get('/system/ip-whitelist'))
}

export function searchWhitelistUsers(keyword: string): Promise<{ items: WhitelistUser[] }> {
  return request(http.get('/system/ip-whitelist/user-options', { params: { keyword } }))
}

export function createIpWhitelist(payload: IpWhitelistPayload): Promise<IpWhitelistItem> {
  return request(http.post('/system/ip-whitelist', payload))
}

export function updateIpWhitelist(id: string, payload: IpWhitelistPayload): Promise<IpWhitelistItem> {
  return request(http.put(`/system/ip-whitelist/${id}`, payload))
}

export function deleteIpWhitelist(id: string): Promise<{ id: string }> {
  return request(http.delete(`/system/ip-whitelist/${id}`))
}
