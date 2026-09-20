<script setup lang="ts">
import { computed } from 'vue'
import { House, Setting, Document, Collection, Close, User, Tickets } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { pathForRouteName } from '@/router/menu'
import UserAccountMenu from './UserAccountMenu.vue'

withDefaults(defineProps<{ collapsed?: boolean; mobile?: boolean }>(), { collapsed: false, mobile: false })
defineEmits<{ select: []; close: [] }>()

const auth = useAuthStore()
const route = useRoute()
const tree = computed(() => auth.visibleMenus
  .filter(item => item.parent_id === null)
  .sort((a, b) => Number(a.title.includes('系统')) - Number(b.title.includes('系统')) || a.sort_order - b.sort_order))

function childrenOf(id: string) {
  return auth.visibleMenus.filter(item => item.parent_id === id).sort((a, b) => a.sort_order - b.sort_order)
}

function iconFor(title: string) {
  if (title.includes('系统')) return Setting
  if (title.includes('码表')) return Collection
  if (title.includes('客户')) return User
  if (title.includes('招投标')) return Tickets
  return Document
}
</script>

<template>
  <nav
    class="admin-navigation"
    :class="{ 'is-collapsed': collapsed, 'is-mobile': mobile }"
    aria-label="主导航"
  >
    <div
      class="admin-navigation__brand"
      :title="collapsed ? '业务数据运营平台' : undefined"
      aria-label="业务数据运营平台"
    >
      <span
        class="admin-brand-mark"
        aria-hidden="true"
      ><i /><i /><i /></span>
      <div v-if="!collapsed">
        业务数据运营平台<small>统一工作空间</small>
      </div>
      <button
        v-if="mobile"
        type="button"
        class="admin-navigation__close"
        aria-label="关闭导航菜单"
        @click="$emit('close')"
      >
        <el-icon><Close /></el-icon>
      </button>
    </div>
    <div class="admin-navigation__scroll">
      <el-menu
        :default-active="route.path"
        :collapse="collapsed"
        :collapse-transition="false"
        popper-class="admin-navigation-popper"
        router
        @select="$emit('select')"
      >
        <el-menu-item
          index="/"
          aria-label="首页"
        >
          <el-icon><House /></el-icon>
          <template #title>
            首页
          </template>
        </el-menu-item>
        <template
          v-for="item in tree"
          :key="item.id"
        >
          <el-sub-menu
            v-if="childrenOf(item.id).length"
            :index="item.id"
            :aria-label="item.title"
            :class="{ 'has-active-child': childrenOf(item.id).some(child => pathForRouteName(child.route_name) === route.path) }"
          >
            <template #title>
              <el-icon><component :is="iconFor(item.title)" /></el-icon>
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
            :aria-label="item.title"
          >
            <el-icon><component :is="iconFor(item.title)" /></el-icon>
            <template #title>
              {{ item.title }}
            </template>
          </el-menu-item>
        </template>
      </el-menu>
    </div>
    <div class="admin-navigation__footer">
      <UserAccountMenu :compact="collapsed && !mobile" />
    </div>
  </nav>
</template>

<style scoped>
.admin-navigation { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; background: var(--zt-nav); }
.admin-navigation__brand { display: flex; flex-shrink: 0; align-items: center; gap: 10px; height: 88px; padding: 0 20px; color: #f4f8ff; font-size: 16px; font-weight: 650; white-space: nowrap; }
.admin-navigation__brand small { display: block; margin-top: 6px; color: #93abc9; font-size: 10px; font-weight: 400; letter-spacing: 2px; }
.admin-brand-mark { display: flex; flex-shrink: 0; align-items: center; gap: 3px; }
.admin-brand-mark i { width: 5px; height: 22px; border-radius: 2px; background: #c8defa; transform: skewY(-24deg); }
.admin-brand-mark i:nth-child(2) { height: 30px; background: #fff; }
.admin-brand-mark i:nth-child(3) { background: #80aaf0; }
.admin-navigation__scroll { flex: 1; min-height: 0; overflow: auto; }
.admin-navigation :deep(.el-menu) { --el-menu-bg-color: transparent; --el-menu-text-color: var(--zt-nav-text); --el-menu-active-color: #fff; --el-menu-hover-bg-color: #ffffff0c; width: 100%; border-right: none; padding: 6px 0; }
.admin-navigation :deep(.el-menu-item), .admin-navigation :deep(.el-sub-menu__title) { height: 44px; margin: 3px 12px; border-radius: 7px; font-size: 14px; }
.admin-navigation :deep(.el-sub-menu .el-menu-item) { min-width: 0; padding-left: 47px !important; }
.admin-navigation :deep(.el-menu-item.is-active) { background: var(--zt-nav-active); font-weight: 600; box-shadow: inset 3px 0 #93b9f1; }
.admin-navigation :deep(.el-menu-item:hover), .admin-navigation :deep(.el-sub-menu__title:hover) { color: #fff; }
.admin-navigation :deep(.el-menu-item.is-active:hover) { background: var(--zt-nav-active); }
.admin-navigation :deep(.el-menu-item:focus-visible), .admin-navigation :deep(.el-sub-menu__title:focus-visible) { outline: 2px solid #93b9f1; outline-offset: -2px; }
.admin-navigation__footer { flex-shrink: 0; padding: 10px 12px 16px; border-top: 1px solid #ffffff14; }
.is-collapsed .admin-navigation__footer { padding: 10px 8px 16px; }
.is-collapsed .admin-navigation__brand { justify-content: center; padding: 0; }
.is-collapsed :deep(.el-menu-item), .is-collapsed :deep(.el-sub-menu__title) { margin: 3px 8px; padding: 0 12px !important; }
.is-collapsed :deep(.el-menu-item .el-menu-tooltip__trigger) { padding: 0 12px !important; }
.is-collapsed :deep(.has-active-child > .el-sub-menu__title) { background: var(--zt-nav-active); color: #fff; box-shadow: inset 3px 0 #93b9f1; }
.admin-navigation__close { display: grid; place-items: center; flex: 0 0 44px; width: 44px; height: 44px; margin-left: auto; padding: 0; border: 0; border-radius: 6px; color: #d3e2f5; background: transparent; cursor: pointer; font-size: 20px; }
.admin-navigation__close:hover { background: #ffffff14; }
.admin-navigation__close:focus-visible { outline: 2px solid #93b9f1; }
@media (max-width: 1000px) { .admin-navigation__brand { gap: 8px; padding: 0 18px; font-size: 14px; } }
.is-mobile .admin-navigation__brand { gap: 10px; height: 80px; padding: 0 16px; font-size: 16px; }
@media (max-width: 359px) { .is-mobile .admin-navigation__brand { gap: 8px; padding: 0 12px; font-size: 14px; } }
</style>

<style>
.admin-navigation-popper { --el-menu-bg-color: #1c3a60; --el-menu-text-color: var(--zt-nav-text); --el-menu-active-color: #fff; --el-menu-hover-bg-color: #33567e; border-color: #33567e !important; }
.admin-navigation-popper .el-menu-item { border-radius: 6px; margin: 3px 6px; }
.admin-navigation-popper .el-menu-item.is-active { background: var(--zt-nav-active); }
.admin-navigation-popper .el-menu-item:focus-visible { outline: 2px solid #93b9f1; outline-offset: -2px; }
</style>
