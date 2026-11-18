import { defineStore } from 'pinia'

import { changePassword, fetchMe, fetchPermissions, login, logout, logoutAll } from '@/api/auth'
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
import { canExport, canRead, canWrite } from '@/permissions/levels'

/** 会话真没了（IAM 明确拒绝）才清身份：续期被拒是带 response 的原始错误，取个人信息被拒是 ApiRequestError.status。 */
function sessionRejected(error: unknown): boolean {
  const failure = error as { status?: number; response?: { status?: number } } | null
  const status = failure?.response?.status ?? failure?.status
  return status === 401 || status === 403
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as MePayload | null,
    resources: [] as ResourceLevel[],
    menus: [] as MenuItem[],
    mustChangePassword: false,
    bootstrapped: false,
    restoring: false,
    /** 启动时服务暂时不可用（IAM 重启、网关 502、断网）：不清身份，下次进页面再试。 */
    unavailable: false,
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
    canExport:
      (state) =>
      (code: string): boolean =>
        canExport(state.resources.find((item) => item.code === code)?.level),
    canFull:
      (state) =>
      (code: string): boolean =>
        canWrite(state.resources.find((item) => item.code === code)?.level),
    isSuperadmin: (state): boolean => Boolean(state.user?.is_superadmin),
    visibleMenus(state): MenuItem[] {
      const byId = new Map<string, MenuItem>()
      const byParent = new Map<string | null, MenuItem[]>()
      for (const menu of state.menus) {
        byId.set(menu.id, menu)
        const list = byParent.get(menu.parent_id) ?? []
        list.push(menu)
        byParent.set(menu.parent_id, list)
      }
      const hasLeaf = (menu: MenuItem): boolean => {
        if (menu.route_name) {
          return true
        }
        const children = byParent.get(menu.id) ?? []
        return children.some(child => hasLeaf(child))
      }
      const rootOf = (menu: MenuItem): MenuItem => {
        let cur = menu
        while (cur.parent_id && byId.has(cur.parent_id)) {
          cur = byId.get(cur.parent_id)!
        }
        return cur
      }
      // 顶级模块目录无任何可见叶子时整体隐藏；同一顶级模块下的子级空目录（如「智库码表」）对拥有该模块权限的用户保留。
      return state.menus.filter(menu => {
        if (menu.parent_id === null) return hasLeaf(menu)
        return menu.route_name ? true : hasLeaf(rootOf(menu))
      })
    },
  },
  actions: {
    async bootstrap(): Promise<void> {
      if (this.bootstrapped || this.restoring) {
        return
      }
      this.restoring = true
      this.unavailable = false
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
        this.bootstrapped = true
      } catch (error) {
        if (sessionRejected(error)) {
          setAccessToken('')
          this.signedIn = false
          this.clearIdentity()
          this.bootstrapped = true
        } else {
          // 部署时刷新页面、新开标签页：原来不分原因一律清身份、跳登录页，会话其实还在。
          this.unavailable = true
        }
      } finally {
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
      } catch {
        // 服务端失败不阻塞退出，本地照常清理。
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
