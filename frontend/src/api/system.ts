import { postExcelImport, type ImportResult, type ImportStage } from './excelImport'
import { http, request } from './http'
import type {
  EffectivePermission,
  FilterParam,
  GrantItem,
  OnlineSession,
  Page,
  ResourceNode,
  RoleItem,
  RoleMember,
  UserItem,
} from './types'

/** 角色筛选里的特殊值：还没分配任何角色的账号。 */
export const NO_ROLE = 'none'

/**
 * 用户列表、详情里的一行，带上当前操作人能不能管这个人（停用、删除、重置密码、下线、解锁）。
 * 不是超级管理员的看超级管理员时为 false，页面据此不给这些按钮（点了后端也会拒绝）。
 */
export type ManagedUser = UserItem & { can_manage?: boolean }

/** 在线用户页的一台设备：全部有效登录里，标出是否在线、是不是我正在用的这台、我能不能把它下线。 */
export interface OnlineDevice extends OnlineSession {
  /** 最近 online_window_seconds（30 分钟）内有过操作。 */
  online: boolean
  /** 当前操作人正在用的这台设备；不给下线，要退出用「退出登录」。 */
  current: boolean
  can_manage: boolean
}

export function listUsers(params: {
  page?: number
  page_size?: number
  username?: FilterParam
  /** 同时匹配用户名、显示名、电话、邮箱。 */
  keyword?: FilterParam
  status?: FilterParam
  /** 角色 id，或 NO_ROLE 表示待分配角色。 */
  role_id?: FilterParam
  sort?: string
}): Promise<Page<ManagedUser>> {
  return request(http.get('/system/users', { params }))
}

/** 批量建账号。结果文件（含初始密码、跳过的行）会自动下载，只给这一次。 */
export function importUsers(file: File, onProgress?: (percent: number, stage: ImportStage) => void): Promise<ImportResult> {
  return postExcelImport('/system/users/import', file, onProgress)
}

export function getUser(userId: string): Promise<ManagedUser> {
  return request(http.get(`/system/users/${userId}`))
}

export function createUser(payload: {
  username: string
  display_name: string
  phone?: string
  email?: string
  password?: string
  role_ids?: string[]
}): Promise<{ user: UserItem; temporary_password?: string }> {
  return request(http.post('/system/users', payload))
}

export function updateUser(
  userId: string,
  payload: { display_name?: string; phone?: string; email?: string; status?: 'active' | 'disabled'; version: number },
): Promise<UserItem> {
  return request(http.patch(`/system/users/${userId}`, payload))
}

export function deleteUser(userId: string): Promise<{ deleted: boolean }> {
  return request(http.delete(`/system/users/${userId}`))
}

export function resetUserPassword(userId: string): Promise<{ temporary_password: string }> {
  return request(http.post(`/system/users/${userId}/reset-password`))
}

export function revokeUserSessions(userId: string): Promise<{ revoked: number }> {
  return request(http.post(`/system/users/${userId}/revoke-sessions`))
}

/** 角色之外单独给这个人的授权。 */
export function getUserGrants(userId: string): Promise<{ grants: GrantItem[]; version: number }> {
  return request(http.get(`/system/users/${userId}/grants`))
}

/** version 是打开时拿到的用户版本号：两个人同时改同一个人，后保存的会收到 409，不会悄悄盖掉先保存的。 */
export function replaceUserGrants(
  userId: string,
  grants: { resource_code: string; level: string }[],
  version: number,
): Promise<{ grants: GrantItem[]; version: number }> {
  return request(http.put(`/system/users/${userId}/grants`, { grants, version }))
}

/** 密码连续输错被锁的账号，不等到期直接解锁。 */
export function unlockUser(userId: string): Promise<{ unlocked: boolean }> {
  return request(http.post(`/system/users/${userId}/unlock`))
}

/** 解除一个出口 IP 的登录限制（同一出口输错太多次，所有人都登不上）。只有超级管理员能做。 */
export function unlockLoginIp(ip: string): Promise<{ unlocked: boolean }> {
  return request(http.post('/system/login-limits/unlock-ip', { ip }))
}

/** 在线用户页：全部有效登录（没撤销、没过期的会话），每台设备一行，online 标出 30 分钟内有操作的。 */
export function listOnlineSessions(): Promise<{ items: OnlineDevice[]; online_window_seconds: number }> {
  return request(http.get('/system/sessions'))
}

export function revokeOnlineSession(sessionId: string): Promise<{ revoked: boolean }> {
  return request(http.delete(`/system/sessions/${sessionId}`))
}

export function replaceUserRoles(userId: string, payload: { role_ids: string[]; version: number }): Promise<UserItem> {
  return request(http.put(`/system/users/${userId}/roles`, payload))
}

export function listRoles(params: {
  page?: number
  page_size?: number
  status?: FilterParam
  name?: FilterParam
}): Promise<Page<RoleItem>> {
  return request(http.get('/system/roles', { params }))
}

export function getRole(roleId: string): Promise<RoleItem> {
  return request(http.get(`/system/roles/${roleId}`))
}

export function createRole(payload: { code?: string; name: string; description?: string }): Promise<RoleItem> {
  return request(http.post('/system/roles', payload))
}

export function updateRole(
  roleId: string,
  payload: { name?: string; description?: string; status?: 'active' | 'disabled'; version: number },
): Promise<RoleItem> {
  return request(http.patch(`/system/roles/${roleId}`, payload))
}

export function listRoleGrants(roleId: string): Promise<{ role: RoleItem; grants: GrantItem[] }> {
  return request(http.get(`/system/roles/${roleId}/grants`))
}

export function replaceRoleGrants(
  roleId: string,
  payload: { version: number; grants: { resource_code: string; level: 'NONE' | 'READ' | 'EXPORT' | 'FULL' }[] },
): Promise<{ role: RoleItem; grants: GrantItem[] }> {
  return request(http.put(`/system/roles/${roleId}/grants`, payload))
}

export function listResourceTree(): Promise<{ tree: ResourceNode[] }> {
  return request(http.get('/system/resources'))
}

// Role pickers must not silently omit roles beyond the first API page.
export async function listAllRoles(): Promise<RoleItem[]> {
  const items: RoleItem[] = []
  let page = 1
  while (true) {
    const result = await listRoles({ page, page_size: 100 })
    items.push(...result.items)
    if (!result.items.length || items.length >= result.total) return items
    page += 1
  }
}

/** 以现有角色为模板新建：复制模块授权，不复制成员。 */
export function copyRole(roleId: string, payload: { name: string; description?: string }): Promise<RoleItem> {
  return request(http.post(`/system/roles/${roleId}/copy`, payload))
}

export function listRoleMembers(roleId: string): Promise<{ items: RoleMember[] }> {
  return request(http.get(`/system/roles/${roleId}/members`))
}

export function addRoleMembers(roleId: string, userIds: string[]): Promise<{ added: number; items: RoleMember[] }> {
  return request(http.post(`/system/roles/${roleId}/members`, { user_ids: userIds }))
}

export function removeRoleMember(roleId: string, userId: string): Promise<{ items: RoleMember[] }> {
  return request(http.delete(`/system/roles/${roleId}/members/${userId}`))
}

/** 多个角色叠加后，这个人在每个模块上最终能做什么。 */
export function getUserPermissions(userId: string): Promise<{ account_active: boolean; items: EffectivePermission[] }> {
  return request(http.get(`/system/users/${userId}/permissions`))
}
