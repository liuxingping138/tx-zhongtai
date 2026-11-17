import { http, request } from './http'
import type { MePayload, PermissionPayload, TokenPayload } from './types'

export function login(username: string, password: string): Promise<TokenPayload> {
  return request(http.post('/auth/login', { username, password }))
}

export function fetchMe(): Promise<MePayload> {
  return request(http.get('/auth/me'))
}

export function fetchPermissions(): Promise<PermissionPayload> {
  return request(http.get('/auth/permissions'))
}

export function changePassword(oldPassword: string, newPassword: string): Promise<TokenPayload> {
  return request(http.put('/auth/password', { old_password: oldPassword, new_password: newPassword }))
}

export function logout(): Promise<null> {
  return request(http.post('/auth/logout'))
}

export function logoutAll(): Promise<{ revoked: number }> {
  return request(http.post('/auth/logout-all'))
}
