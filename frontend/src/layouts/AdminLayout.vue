<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowDown, Fold, Expand, Menu } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'
import AdminNavigation from './AdminNavigation.vue'
import { pathForRouteName } from '@/router/menu'
import { errorMessage } from '@/api/errors'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const storageKey = 'tx-zhongtai-sidebar-collapsed'
const mobileQuery = window.matchMedia('(max-width: 767px)')
const compactQuery = window.matchMedia('(max-width: 1000px)')
const isMobile = ref(mobileQuery.matches)
const isCompact = ref(compactQuery.matches)
const mobileOpen = ref(false)

function savedCollapsed(): boolean {
  try {
    const saved = localStorage.getItem(storageKey)
    if (saved !== null) return saved === 'true'
  } catch { /* Storage can be unavailable in restricted browser contexts. */ }
  return compactQuery.matches
}

const collapsed = ref(savedCollapsed())
const sidebarWidth = computed(() => collapsed.value ? '64px' : isCompact.value ? '190px' : '220px')
const toggleLabel = computed(() => isMobile.value ? '打开导航菜单' : collapsed.value ? '展开侧栏' : '收起侧栏')

function toggleNavigation() {
  if (isMobile.value) {
    mobileOpen.value = true
    return
  }
  collapsed.value = !collapsed.value
  try {
    localStorage.setItem(storageKey, String(collapsed.value))
  } catch { /* The current session still supports collapsing without storage. */ }
}

function syncViewport() {
  isMobile.value = mobileQuery.matches
  isCompact.value = compactQuery.matches
  mobileOpen.value = false
}

mobileQuery.addEventListener('change', syncViewport)
compactQuery.addEventListener('change', syncViewport)
onBeforeUnmount(() => {
  mobileQuery.removeEventListener('change', syncViewport)
  compactQuery.removeEventListener('change', syncViewport)
})
watch(() => route.fullPath, () => { mobileOpen.value = false })

const crumbs = computed(() => {
  const current = auth.visibleMenus.find(item => pathForRouteName(item.route_name) === route.path)
  const parent = current?.parent_id ? auth.visibleMenus.find(item => item.id === current.parent_id) : undefined
  return [
    ...(route.path !== '/' ? [{ title: '工作台', path: '/' }] : []),
    ...(parent ? [{ title: parent.title, path: undefined }] : []),
    { title: route.meta.title || '工作台', path: undefined },
  ]
})

async function onLogout() {
  try {
    await auth.signOut()
  } catch (error) {
    ElMessage.error(errorMessage(error, '退出失败'))
  } finally {
    await router.push({ name: 'login' })
  }
}
</script>

<template>
  <el-container class="admin-layout">
    <el-aside
      v-if="!isMobile"
      id="desktop-navigation"
      :width="sidebarWidth"
      class="admin-layout__aside"
    >
      <AdminNavigation :collapsed="collapsed" />
    </el-aside>
    <el-drawer
      v-if="isMobile"
      id="mobile-navigation"
      v-model="mobileOpen"
      title="导航菜单"
      direction="ltr"
      size="min(280px, 86vw)"
      :with-header="false"
      class="admin-navigation-drawer"
    >
      <AdminNavigation
        mobile
        @close="mobileOpen = false"
        @select="mobileOpen = false"
      />
    </el-drawer>
    <el-container class="admin-layout__content">
      <el-header class="admin-layout__header">
        <div class="admin-layout__header-start">
          <button
            type="button"
            class="admin-layout__toggle"
            :aria-label="toggleLabel"
            :title="toggleLabel"
            :aria-expanded="isMobile ? mobileOpen : !collapsed"
            :aria-controls="isMobile ? 'mobile-navigation' : 'desktop-navigation'"
            @click="toggleNavigation"
          >
            <el-icon><component :is="isMobile ? Menu : collapsed ? Expand : Fold" /></el-icon>
          </button>
          <el-breadcrumb>
            <el-breadcrumb-item
              v-for="crumb in crumbs"
              :key="crumb.title"
              :to="crumb.path"
            >
              {{ crumb.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <el-dropdown trigger="click">
          <el-button
            text
            class="admin-layout__user"
          >
            <span
              class="admin-layout__avatar"
              aria-hidden="true"
            >{{ (auth.user?.display_name || auth.user?.username || '用').slice(0, 1) }}</span>
            <span class="admin-layout__username">{{ auth.user?.display_name || auth.user?.username }}</span>
            <el-icon><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="router.push({ name: 'profile' })">
                个人设置
              </el-dropdown-item>
              <el-dropdown-item @click="onLogout">
                退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin-layout { height: 100vh; height: 100dvh; background: var(--zt-soft); }
.admin-layout__aside { flex-shrink: 0; overflow: hidden; background: var(--zt-nav); transition: width .2s ease; }
.admin-layout__header-start { display: flex; align-items: center; gap: 16px; min-width: 0; }
.admin-layout__header-start :deep(.el-breadcrumb) { min-width: 0; line-height: 1.5; }
.admin-layout__toggle { display: grid; place-items: center; flex: 0 0 36px; width: 36px; height: 36px; padding: 0; border: 0; border-radius: 8px; color: var(--zt-ink-700); background: transparent; cursor: pointer; font-size: 20px; }
.admin-layout__toggle:hover { color: var(--zt-blue-600); background: #eef3fa; }
.admin-layout__toggle:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.admin-layout__username { max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.admin-layout__content { min-width: 0; }
.admin-layout__header { display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; height: 60px; padding: 0 28px; background: #fff; border-bottom: 1px solid var(--zt-border); }
.admin-layout :deep(.el-main) { padding: 24px 28px; background: var(--zt-soft); }
.admin-layout__user { display: inline-flex; align-items: center; gap: 10px; padding: 5px 0 5px 8px; border: 0; border-radius: 6px; background: transparent; color: var(--zt-ink-700); font: inherit; font-size: 13px; cursor: pointer; }
.admin-layout__user:hover { background: var(--zt-soft); }
.admin-layout__user:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 4px; }
.admin-layout__avatar { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 9px; background: #eaf0f8; color: #3a608e; font-size: 12px; }
@media (max-width: 1000px) { .admin-layout :deep(.el-main) { padding: 20px; } }
@media (max-width: 767px) {
  .admin-layout__header { height: 60px; gap: 12px; padding: 0 12px; }
  .admin-layout__header-start { gap: 8px; }
  .admin-layout__username { max-width: 72px; }
  .admin-layout__header-start :deep(.el-breadcrumb__item:not(:last-child)) { display: none; }
  .admin-layout__user { flex-shrink: 0; gap: 6px; }
  .admin-layout :deep(.el-main) { padding: 16px 12px; }
}
@media (prefers-reduced-motion: reduce) { .admin-layout__aside { transition: none; } }
</style>

<style>
.admin-navigation-drawer .el-drawer__body { display: flex; padding: 0; min-height: 0; }
</style>
