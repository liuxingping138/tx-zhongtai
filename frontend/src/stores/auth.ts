import { defineStore } from 'pinia'

import { changePassword, fetchMe, fetchPermissions, login, logout, logoutAll } from '@/api/auth'
import { errorMessage } from '@/api/errors'
import {
  armAccessRefresh,
  broadcastLogout,
  disarmAccessRefresh,
  ensureCsrfToken,
  getAccessToken,
  refreshSession,
  setAccessToken,
  setCsrfToken,
} from '@/api/session'
import type { MePayload, MenuItem, ResourceLevel } from '@/api/types'
import { canRead, canWrite } from '@/permissions/levels'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as MePayload | null,
    resources: [] as ResourceLevel[],
    menus: [] as MenuItem[],
    mustChangePassword: false,
    bootstrapped: false,
    restoring: false,
    signedIn: false,
  }),
  getters: {
    isAuthenticated: (state): boolean => state.signedIn && Boolean(getAccessToken()),
    resourceLevel:
      (state) =>
      (code: string): string | null =>
        state.resources.find((item) => item.code === code)?.level ?? null,
    canRead:
      (state) =>
      (code: string): boolean =>
        canRead(state.resources.find((item) => item.code === code)?.level),
    canFull:
      (state) =>
      (code: string): boolean =>
        canWrite(state.resources.find((item) => item.code === code)?.level),
    isSuperadmin: (state): boolean => Boolean(state.user?.is_superadmin),
    visibleMenus(state): MenuItem[] {
      const byParent = new Map<string | null, MenuItem[]>()
      for (const menu of state.menus) {
        const list = byParent.get(menu.parent_id) ?? []
        list.push(menu)
        byParent.set(menu.parent_id, list)
      }
      const hasLeaf = (menu: MenuItem): boolean => {
        if (menu.route_name) {
          return true
        }
        const children = byParent.get(menu.id) ?? []
        return children.some((child) => hasLeaf(child))
      }
      return state.menus.filter((menu) => hasLeaf(menu))
    },
  },
  actions: {
    async bootstrap(): Promise<void> {
      if (this.bootstrapped || this.restoring) {
        return
      }
      this.restoring = true
      try {
        await ensureCsrfToken()
        if (!getAccessToken()) {
          const token = await refreshSession()
          this.signedIn = true
          this.mustChangePassword = token.must_change_password
        }
        if (getAccessToken()) {
          this.signedIn = true
          await this.loadProfile()
        }
      } catch {
        setAccessToken('')
        this.clearIdentity()
      } finally {
        this.bootstrapped = true
        this.restoring = false
      }
    },
    async loadProfile(): Promise<void> {
      this.user = await fetchMe()
      this.mustChangePassword = this.user.must_change_password
      if (!this.mustChangePassword) {
        const permissions = await fetchPermissions()
        this.resources = permissions.resources
        this.menus = permissions.menus
      } else {
        this.resources = []
        this.menus = []
      }
    },
    async signIn(username: string, password: string): Promise<void> {
      const token = await login(username, password)
      setAccessToken(token.access_token)
      armAccessRefresh(token.expires_in)
      this.signedIn = true
      await ensureCsrfToken()
      this.mustChangePassword = token.must_change_password
      await this.loadProfile()
    },
    async updatePassword(oldPassword: string, newPassword: string): Promise<void> {
      const token = await changePassword(oldPassword, newPassword)
      setAccessToken(token.access_token)
      armAccessRefresh(token.expires_in)
      this.signedIn = true
      this.mustChangePassword = false
      await this.loadProfile()
    },
    async signOut(): Promise<void> {
      try {
        await ensureCsrfToken()
        await logout()
      } catch (error) {
        if (errorMessage(error) && getAccessToken()) {
          // 本地仍清理；服务端失败不阻塞退出。
        }
      } finally {
        this.clearSession()
      }
    },
    async signOutAll(): Promise<number> {
      await ensureCsrfToken()
      const result = await logoutAll()
      this.clearSession()
      return result.revoked
    },
    clearIdentity(): void {
      this.user = null
      this.resources = []
      this.menus = []
      this.mustChangePassword = false
    },
    clearSession(): void {
      disarmAccessRefresh()
      setAccessToken('')
      setCsrfToken('')
      this.signedIn = false
      this.clearIdentity()
      broadcastLogout()
    },
  },
})
