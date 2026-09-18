import { http, request } from './http'
import type { GrantItem, Page, ResourceNode, RoleItem, UserItem } from './types'

export function listUsers(params: {
  page?: number
  page_size?: number
  username?: string
  status?: string
  sort?: string
}): Promise<Page<UserItem>> {
  return request(http.get('/system/users', { params }))
}

export function getUser(userId: string): Promise<UserItem> {
  return request(http.get(`/system/users/${userId}`))
}

export function createUser(payload: {
  username: string
  display_name: string
  password?: string
}): Promise<{ user: UserItem; temporary_password?: string }> {
  return request(http.post('/system/users', payload))
}

export function updateUser(
  userId: string,
  payload: { display_name?: string; status?: 'active' | 'disabled' | 'archived'; version: number },
): Promise<UserItem> {
  return request(http.patch(`/system/users/${userId}`, payload))
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

export function listRoles(params: { page?: number; page_size?: number; status?: string }): Promise<Page<RoleItem>> {
  return request(http.get('/system/roles', { params }))
}

export function getRole(roleId: string): Promise<RoleItem> {
  return request(http.get(`/system/roles/${roleId}`))
}

export function createRole(payload: { code: string; name: string }): Promise<RoleItem> {
  return request(http.post('/system/roles', payload))
}

export function updateRole(
  roleId: string,
  payload: { name?: string; status?: 'active' | 'disabled'; version: number },
): Promise<RoleItem> {
  return request(http.patch(`/system/roles/${roleId}`, payload))
}

export function listRoleGrants(roleId: string): Promise<{ role: RoleItem; grants: GrantItem[] }> {
  return request(http.get(`/system/roles/${roleId}/grants`))
}

export function replaceRoleGrants(
  roleId: string,
  payload: { version: number; grants: { resource_code: string; level: 'NONE' | 'READ' | 'FULL' }[] },
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
