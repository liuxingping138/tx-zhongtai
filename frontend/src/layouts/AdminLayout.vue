<script setup lang="ts">
import { computed } from 'vue'
import { House, Setting, Document, Collection, ArrowDown } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'
import { pathForRouteName } from '@/router/menu'
import type { MenuItem } from '@/api/types'
import { errorMessage } from '@/api/errors'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const tree = computed(() => {
  const items = auth.visibleMenus
  const childrenOf = new Map<string | null, MenuItem[]>()
  for (const item of items) {
    const list = childrenOf.get(item.parent_id) ?? []
    list.push(item)
    childrenOf.set(item.parent_id, list)
  }
  for (const list of childrenOf.values()) {
    list.sort((a, b) => a.sort_order - b.sort_order)
  }
  return childrenOf.get(null) ?? []
})

function childrenOf(id: string): MenuItem[] {
  return auth.visibleMenus
    .filter((item) => item.parent_id === id)
    .sort((a, b) => a.sort_order - b.sort_order)
}

const active = computed(() => route.path)

const crumbs = computed(() => {
  const titles = route.matched.map((item) => item.meta.title).filter((title): title is string => Boolean(title))
  return titles
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
      width="220px"
      class="admin-layout__aside"
    >
      <div class="admin-layout__brand">
        <span
          class="admin-brand-mark"
          aria-hidden="true"
        ><i /><i /><i /></span>
        <div>中台管理端<small>统一工作空间</small></div>
      </div>
      <el-menu
        :default-active="active"
        router
      >
        <el-menu-item index="/">
          <el-icon><House /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <template
          v-for="item in tree"
          :key="item.id"
        >
          <el-sub-menu
            v-if="childrenOf(item.id).length"
            :index="item.id"
          >
            <template #title>
              <el-icon><component :is="item.title.includes('系统') ? Setting : item.title.includes('码表') ? Collection : Document" /></el-icon>
              <span>{{ item.title }}</span>
            </template>
            <el-menu-item
              v-for="child in childrenOf(item.id)"
              :key="child.id"
              :index="pathForRouteName(child.route_name) || child.id"
            >
              {{ child.title }}
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item
            v-else-if="pathForRouteName(item.route_name)"
            :index="pathForRouteName(item.route_name) || item.id"
          >
            {{ item.title }}
          </el-menu-item>
        </template>
      </el-menu>
      <div class="admin-layout__aside-footer">
        信息有序 · 协作高效
      </div>
    </el-aside>
    <el-container class="admin-layout__content">
      <el-header class="admin-layout__header">
        <el-breadcrumb>
          <el-breadcrumb-item
            v-for="title in crumbs"
            :key="title"
          >
            {{ title }}
          </el-breadcrumb-item>
        </el-breadcrumb>
        <el-dropdown trigger="click">
          <button
            type="button"
            class="admin-layout__user"
          >
            <span
              class="admin-layout__avatar"
              aria-hidden="true"
            >{{ (auth.user?.display_name || auth.user?.username || '用').slice(0, 1) }}</span>
            {{ auth.user?.display_name || auth.user?.username }}
            <el-icon><ArrowDown /></el-icon>
          </button>
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
.admin-layout__aside { display: flex; flex-direction: column; background: linear-gradient(175deg, #172f50, #1c3a60); border-right: 1px solid #172f50; }
.admin-layout__brand { display: flex; align-items: center; gap: 12px; min-height: 92px; padding: 0 24px; color: #f4f8ff; font-size: 17px; font-weight: 650; letter-spacing: .5px; }
.admin-layout__brand small { display: block; margin-top: 6px; color: #93abc9; font-size: 10px; font-weight: 400; letter-spacing: 2px; }
.admin-brand-mark { display: flex; align-items: center; gap: 3px; }
.admin-brand-mark i { width: 5px; height: 22px; border-radius: 2px; background: #c8defa; transform: skewY(-24deg); }
.admin-brand-mark i:nth-child(2) { height: 30px; background: #fff; }
.admin-brand-mark i:nth-child(3) { background: #80aaf0; }
.admin-layout__aside :deep(.el-menu) { border-right: none; padding: 6px 0; background: transparent; }
.admin-layout__aside :deep(.el-menu-item), .admin-layout__aside :deep(.el-sub-menu__title) { height: 44px; margin: 3px 12px; border-radius: 7px; color: #b9cbe1; font-size: 13px; }
.admin-layout__aside :deep(.el-sub-menu .el-menu-item) { min-width: 0; padding-left: 47px !important; }
.admin-layout__aside :deep(.el-menu-item.is-active) { background: #33567e; color: #fff; font-weight: 600; box-shadow: inset 3px 0 #93b9f1; }
.admin-layout__aside :deep(.el-menu-item:hover), .admin-layout__aside :deep(.el-sub-menu__title:hover) { background: #ffffff0c; color: #fff; }
.admin-layout__aside :deep(.el-menu-item.is-active:hover) { background: #33567e; }
.admin-layout__aside-footer { margin-top: auto; padding: 24px; color: #93abc9; font-size: 11px; letter-spacing: 1px; }
.admin-layout__content { min-width: 0; }
.admin-layout__header { display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; height: 68px; padding: 0 28px; background: #fff; border-bottom: 1px solid var(--zt-border); }
.admin-layout :deep(.el-main) { padding: 26px 28px; background: var(--zt-soft); }
.admin-layout__user { display: inline-flex; align-items: center; gap: 10px; padding: 5px 0 5px 8px; border: 0; border-radius: 6px; background: transparent; color: var(--zt-ink-700); font: inherit; font-size: 13px; cursor: pointer; }
.admin-layout__user:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 4px; }
.admin-layout__avatar { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 9px; background: #eaf0f8; color: #3a608e; font-size: 12px; }
@media (max-width: 1000px) { .admin-layout__aside { width: 190px !important; } .admin-layout__brand { padding: 0 18px; } .admin-layout :deep(.el-main) { padding: 20px; } }
</style>
