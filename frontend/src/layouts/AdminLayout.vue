<script setup lang="ts">
import { computed } from 'vue'
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
        中台管理端
      </div>
      <el-menu
        :default-active="active"
        router
      >
        <el-menu-item index="/">
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
              {{ item.title }}
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
    </el-aside>
    <el-container>
      <el-header class="admin-layout__header">
        <el-breadcrumb>
          <el-breadcrumb-item
            v-for="title in crumbs"
            :key="title"
          >
            {{ title }}
          </el-breadcrumb-item>
        </el-breadcrumb>
        <el-dropdown>
          <span class="admin-layout__user">
            {{ auth.user?.display_name || auth.user?.username }}
          </span>
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
.admin-layout {
  height: 100vh;
  background: #edf2f8;
}

.admin-layout__aside {
  background: #fff;
  border-right: 1px solid var(--zt-border);
  box-shadow: 2px 0 12px rgba(30, 64, 115, 0.06);
}

.admin-layout__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 64px;
  padding: 0 20px;
  color: var(--zt-blue-900);
  border-bottom: 1px solid var(--zt-border);
  font-size: 16px;
  font-weight: 700;
}

.admin-layout__brand::before {
  width: 4px;
  height: 18px;
  border-radius: 4px;
  background: var(--zt-blue-600);
  content: '';
}

.admin-layout :deep(.el-menu) {
  border-right: none;
  padding: 8px 0;
}

.admin-layout :deep(.el-menu-item),
.admin-layout :deep(.el-sub-menu__title) {
  height: 44px;
  margin: 2px 8px;
  border-radius: 6px;
  color: var(--zt-ink-700);
}

.admin-layout :deep(.el-menu-item.is-active) {
  background: #edf5ff;
  color: var(--zt-blue-700);
  font-weight: 700;
}

.admin-layout :deep(.el-menu-item:hover),
.admin-layout :deep(.el-sub-menu__title:hover) {
  background: #f7f9fc;
}

.admin-layout__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  background: #fff;
  border-bottom: 1px solid var(--zt-border);
  box-shadow: 0 2px 10px rgba(30, 64, 115, 0.04);
}

.admin-layout :deep(.el-main) {
  padding: 20px 24px;
  background: #edf2f8;
}

.admin-layout__user {
  color: var(--zt-ink-700);
  font-weight: 600;
  cursor: pointer;
}
</style>
