import { postExcelImport, type ImportResult, type ImportStage } from './excelImport'
import { http, request } from './http'
import type {
  EffectivePermission,
  FilterParam,
  GrantItem,
  Page,
  ResourceNode,
  RoleItem,
  RoleMember,
  UserItem,
} from './types'

/** 角色筛选里的特殊值：还没分配任何角色的账号。 */
export const NO_ROLE = 'none'

export function listUsers(params: {
  page?: number
  page_size?: number
  username?: FilterParam
  status?: FilterParam
  /** 角色 id，或 NO_ROLE 表示待分配角色。 */
  role_id?: FilterParam
  sort?: string
}): Promise<Page<UserItem>> {
  return request(http.get('/system/users', { params }))
}

/** 批量建账号。结果文件（含初始密码、跳过的行）会自动下载，只给这一次。 */
export function importUsers(file: File, onProgress?: (percent: number, stage: ImportStage) => void): Promise<ImportResult> {
  return postExcelImport('/system/users/import', file, onProgress)
}

export function getUser(userId: string): Promise<UserItem> {
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
