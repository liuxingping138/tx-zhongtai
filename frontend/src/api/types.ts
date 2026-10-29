/** 筛选参数：多选下拉提交多个值，同一字段内是「或」。 */
export type FilterParam = string | string[]

export interface ApiResponse<T> {
  code: string
  message: string
  data: T | null
  request_id: string | null
}

export interface ApiError {
  status: number
  code: string
  message: string
  requestId: string | null
  retryAfter?: string | null
}

export interface TokenPayload {
  access_token: string
  token_type: string
  expires_in: number
  must_change_password: boolean
}

export interface MePayload {
  id: string
  username: string
  display_name: string
  must_change_password: boolean
  status: string
  is_superadmin: boolean
  roles?: string[]
}

export interface ResourceLevel {
  code: string
  level: 'READ' | 'EXPORT' | 'FULL'
}

export interface MenuItem {
  id: string
  parent_id: string | null
  title: string
  route_name: string | null
  resource_code: string | null
  icon: string | null
  sort_order: number
}

export interface PermissionPayload {
  resources: ResourceLevel[]
  menus: MenuItem[]
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface UserItem {
  id: string
  username: string
  display_name: string
  /** 联系方式只做记录展示，没填时是空串。 */
  phone: string
  email: string
  status: 'active' | 'disabled'
  must_change_password: boolean
  /** 最近一次登录成功的时间和 IP；从没登录过是 null 和空串。 */
  last_login_at: string | null
  last_login_ip: string
  /** 密码连续输错被锁，还要锁多少秒；没锁是 0。 */
  locked_seconds?: number
  /** 角色之外单独授权了几个模块（列表里才有）。 */
  direct_grant_count?: number
  version: number
  created_at: string
  updated_at: string
  role_ids?: string[]
  /** 列表与详情都带上角色，页面不必再逐个请求。 */
  roles?: RoleBrief[]
}

export interface OnlineSession {
  id: string
  user: { id: string; username: string; display_name: string }
  ip: string
  user_agent: string
  created_at: string
  last_seen_at: string
}

export interface RoleBrief {
  id: string
  name: string
  status: 'active' | 'disabled'
  is_builtin: boolean
}

export interface RoleItem {
  id: string
  code: string
  name: string
  description?: string
  /** 角色分给了几个人（含已停用账号）。 */
  member_count?: number
  /** 已发布模块上各档的数量：仅查看 / 查看和导出 / 可管理。 */
  grant_counts?: { read: number; export: number; full: number }
  status: 'active' | 'disabled'
  is_builtin: boolean
  version: number
  created_at: string
  updated_at: string
}

export interface GrantItem {
  resource_code: string
  resource_name?: string
  level: 'NONE' | 'READ' | 'EXPORT' | 'FULL'
}

export interface AuditEventItem {
  id: string
  event_id: string
  occurred_at: string
  received_at: string
  source_service: string
  schema_version: number
  request_id: string | null
  actor_id: string | null
  actor_name_snapshot: string | null
  module_code: string | null
  action_code: string | null
  target_type: string | null
  target_id: string | null
  outcome: string
  error_code: string | null
  client_ip: string | null
  user_agent: string | null
  changes: Record<string, unknown> | null
  summary: string | null
  duration_ms: number | null
}

export interface ResourceNode {
  id: string
  code: string
  name: string
  service_code: string
  node_type: 'directory' | 'resource'
  published: boolean
  sort_order: number
  parent_id: string | null
  actions: { action_code: string; required_level: string }[]
  children: ResourceNode[]
}

export interface RoleMember {
  id: string
  username: string
  display_name: string
  status: 'active' | 'disabled'
}

export interface EffectivePermission {
  resource_code: string
  resource_name: string
  group_name: string
  level: 'NONE' | 'READ' | 'EXPORT' | 'FULL'
  /** role_id 为 null 的是单独授权，role_name 写「单独授权」。 */
  sources: { role_id: string | null; role_name: string; level: 'READ' | 'EXPORT' | 'FULL'; active: boolean }[]
}
