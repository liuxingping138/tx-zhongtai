import { defineStore } from 'pinia'

/**
 * 通用 UI 状态（侧边栏折叠等），用于验证 Pinia 接线。
 * 身份/权限状态 store 在 P4 阶段实现（stores/auth.ts、stores/permission.ts）。
 */
export const useAppStore = defineStore('app', {
  state: () => ({
    sidebarCollapsed: false,
  }),
  actions: {
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
    },
  },
})
