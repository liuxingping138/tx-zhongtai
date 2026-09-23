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
  level: 'READ' | 'FULL'
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
  status: 'active' | 'disabled' | 'archived'
  must_change_password: boolean
  version: number
  created_at: string
  updated_at: string
  role_ids?: string[]
  /** 列表与详情都带上角色，页面不必再逐个请求。 */
  roles?: RoleBrief[]
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
  /** 角色分给了几个人（含已禁用账号）。 */
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
  status: 'active' | 'disabled' | 'archived'
}

export interface EffectivePermission {
  resource_code: string
  resource_name: string
  group_name: string
  level: 'NONE' | 'READ' | 'EXPORT' | 'FULL'
  sources: { role_id: string; role_name: string; level: 'READ' | 'EXPORT' | 'FULL'; active: boolean }[]
}
