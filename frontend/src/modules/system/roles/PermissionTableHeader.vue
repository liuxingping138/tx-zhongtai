<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'

import type { ModuleGroup } from '@/permissions/catalog'
import { COLUMNS, openedCount, type Column, type Grants, type PermissionStatusFilter } from '@/permissions/matrix'

defineProps<{
  groups: ModuleGroup[]
  grants: Grants
  keyword: string
  statusFilter: PermissionStatusFilter
  totalModules: number
  totalOpened: number
  totalChanged: number
  allCollapsed: boolean
  hoveredCol: Column | null
  isStuck: boolean
}>()

defineEmits<{
  'update:keyword': [value: string]
  'update:statusFilter': [value: PermissionStatusFilter]
  toggleAll: []
  jumpGroup: [code: string]
}>()
</script>

<template>
  <div
    class="perm-sticky-top"
    :class="{ 'is-stuck': isStuck }"
  >
    <div class="perm-toolbar">
      <div class="perm-toolbar__left">
        <el-input
          :model-value="keyword"
          clearable
          size="default"
          placeholder="搜索菜单或分组，例如省市区"
          aria-label="搜索菜单"
          class="perm-search"
          @update:model-value="$emit('update:keyword', $event)"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <div
          class="perm-filter-chips"
          role="group"
          aria-label="按授权状态筛选"
        >
          <button
            type="button"
            class="perm-filter-chip"
            :class="{ 'is-active': statusFilter === 'ALL' }"
            @click="$emit('update:statusFilter', 'ALL')"
          >
            全部 {{ totalModules }}
          </button>
          <button
            type="button"
            class="perm-filter-chip"
            :class="{ 'is-active': statusFilter === 'OPEN' }"
            @click="$emit('update:statusFilter', 'OPEN')"
          >
            已开通 {{ totalOpened }}
          </button>
          <button
            type="button"
            class="perm-filter-chip"
            :class="{ 'is-active': statusFilter === 'CHANGED' }"
            @click="$emit('update:statusFilter', 'CHANGED')"
          >
            已修改 {{ totalChanged }}
          </button>
        </div>
      </div>
      <div
        v-if="groups.length > 1"
        class="perm-toolbar__right"
      >
        <button
          type="button"
          class="perm-collapse-btn"
          @click="$emit('toggleAll')"
        >
          {{ allCollapsed ? '全部展开' : '全部收起' }}
        </button>
      </div>
    </div>

    <div
      v-if="groups.length > 1"
      class="perm-jump-bar"
      aria-label="快速定位分组"
    >
      <span class="perm-jump-bar__label">快速定位：</span>
      <button
        v-for="group in groups"
        :key="group.code"
        type="button"
        class="perm-jump-pill"
        :class="{ 'has-open': openedCount(group, grants) > 0 }"
        @click="$emit('jumpGroup', group.code)"
      >
        <span>{{ group.name }}</span>
        <span class="perm-jump-pill__count">{{ openedCount(group, grants) }}/{{ group.modules.length }}</span>
      </button>
    </div>

    <div
      class="perm-thead perm-grid-cols"
      role="row"
    >
      <div
        class="perm-th"
        role="columnheader"
      >
        菜单 / 功能模块
      </div>
      <div
        v-for="column in COLUMNS"
        :key="column.level"
        class="perm-th perm-th--col"
        :class="{ 'is-col-hover': hoveredCol === column.level }"
        role="columnheader"
        :title="column.what"
      >
        <strong>{{ column.label }}</strong>
        <small>{{ column.sub }}</small>
      </div>
      <div
        class="perm-th"
        role="columnheader"
      >
        「管理」包含
      </div>
    </div>
  </div>
</template>

<style scoped src="./permission-table.css"></style>
