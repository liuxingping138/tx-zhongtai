<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

import type { EffectivePermission } from '@/api/types'
import { LEVEL_TEXT } from '@/permissions/catalog'

/** 用户的实际权限：多个角色叠加后每个模块取最高一档，并写明每档来自哪个角色。 */
const props = defineProps<{
  permissions: EffectivePermission[]
  accountActive: boolean
  pendingRoleChange: boolean
  error: string
}>()

const keyword = ref('')

const grouped = computed(() => {
  const out = new Map<string, EffectivePermission[]>()
  for (const item of props.permissions) {
    const key = item.group_name || '其他'
    out.set(key, [...(out.get(key) ?? []), item])
  }
  return [...out.entries()]
})

function sourceText(item: EffectivePermission): string {
  return item.sources
    .map(source => `${source.role_name}（${LEVEL_TEXT[source.level]}${source.active ? '' : '，角色已停用'}）`)
    .join('、')
}

const filteredGrouped = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return grouped.value
  const out: [string, EffectivePermission[]][] = []
  for (const [group, items] of grouped.value) {
    const matched = items.filter(item =>
      item.resource_name.toLowerCase().includes(kw)
      || item.resource_code.toLowerCase().includes(kw)
      || group.toLowerCase().includes(kw)
      || sourceText(item).toLowerCase().includes(kw),
    )
    if (matched.length) {
      out.push([group, matched])
    }
  }
  return out
})

const effectiveCount = computed(() => props.permissions.filter(item => item.level !== 'NONE').length)
</script>

<template>
  <section class="block">
    <div class="block__head">
      <div class="block__title-area">
        <h3 class="block__title">
          最终生效权限穿透分析
        </h3>
        <span class="block__hint">多个角色叠加与单独直接授权后取最高一档，共 {{ effectiveCount }} 个模块可用</span>
      </div>
      <el-input
        v-if="permissions.length > 4"
        v-model="keyword"
        clearable
        size="small"
        placeholder="搜索模块名称、编码或来源"
        :prefix-icon="Search"
        aria-label="搜索权限"
        class="block__search"
      />
    </div>

    <el-alert
      v-if="!accountActive"
      type="warning"
      :closable="false"
      show-icon
      title="账号未启用，以下权限暂不生效。"
      class="block__notice"
    />
    <el-alert
      v-if="pendingRoleChange"
      type="info"
      :closable="false"
      show-icon
      title="下面是已保存的权限，保存后按新角色生效。"
      class="block__notice"
    />
    <p
      v-if="error"
      class="muted"
      role="alert"
    >
      {{ error }}
    </p>

    <el-empty
      v-else-if="!permissions.length"
      :image-size="56"
      description="还没有任何模块权限。分配一个角色后，这里会列出能用的模块。"
    />
    <el-empty
      v-else-if="!filteredGrouped.length"
      :image-size="48"
      description="未找到匹配的权限模块"
    />

    <div
      v-else
      class="perm-table-wrap"
    >
      <table class="perm-table">
        <thead>
          <tr>
            <th class="col-module">
              业务模块
            </th>
            <th class="col-level">
              最终生效权限
            </th>
            <th class="col-source">
              权限来源解析
            </th>
            <th class="col-mech">
              授权机制
            </th>
          </tr>
        </thead>
        <tbody
          v-for="[group, items] in filteredGrouped"
          :key="group"
        >
          <tr class="group-row">
            <td colspan="4">
              <div class="group-label">
                <span class="group-bar" />
                <span class="group-name">{{ group }}</span>
                <span class="group-count">共 {{ items.length }} 项</span>
              </div>
            </td>
          </tr>
          <tr
            v-for="item in items"
            :key="item.resource_code"
            class="data-row"
            :class="{ 'is-disabled': item.level === 'NONE' }"
          >
            <td class="col-module">
              <div class="module-title">
                {{ item.resource_name }}
              </div>
              <div class="module-code">
                {{ item.resource_code }}
              </div>
            </td>
            <td class="col-level">
              <span
                class="perm-pill"
                :class="{
                  'perm-pill--full': item.level === 'FULL',
                  'perm-pill--read': item.level === 'READ',
                  'perm-pill--none': item.level === 'NONE',
                }"
              >
                <span
                  class="pill-dot"
                  :class="{
                    'is-full': item.level === 'FULL',
                    'is-read': item.level === 'READ',
                    'is-none': item.level === 'NONE',
                  }"
                />
                {{ item.level === 'NONE' ? '未开通' : LEVEL_TEXT[item.level] }}
              </span>
            </td>
            <td class="col-source">
              <div
                v-if="item.sources.length"
                class="source-list"
              >
                <span
                  v-for="s in item.sources"
                  :key="s.role_id || 'direct'"
                  class="source-badge"
                  :class="{ 'source-badge--direct': s.role_id === null, 'source-badge--inactive': !s.active }"
                >
                  <span class="source-badge__name">{{ s.role_name }}</span>
                  <span class="source-badge__level">({{ LEVEL_TEXT[s.level] }})</span>
                </span>
              </div>
              <span
                v-else
                class="source-empty"
              >未分配角色或单独授权</span>
            </td>
            <td class="col-mech">
              <span
                v-if="item.sources.some(s => !s.active)"
                class="mech-item mech-warn"
              >
                <span class="mech-dot is-warn" />角色已停用
              </span>
              <span
                v-else-if="item.sources.some(s => s.role_id === null)"
                class="mech-item mech-direct"
              >
                <span class="mech-dot is-direct" />单独直配
              </span>
              <span
                v-else-if="item.sources.length"
                class="mech-item mech-inherit"
              >
                <span class="mech-dot is-inherit" />正常继承
              </span>
              <span
                v-else
                class="mech-none"
              >-</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.block { padding: 20px 24px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); box-shadow: var(--zt-shadow); display: flex; flex-direction: column; gap: 16px; }
.block__head { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; padding-bottom: 14px; border-bottom: 1px solid var(--zt-divider); }
.block__title-area { display: flex; flex-direction: column; gap: 4px; }
.block__title { margin: 0; font-size: 16px; font-weight: 650; color: var(--zt-ink-900); }
.block__hint { font-size: 12.5px; color: var(--zt-ink-500); }
.block__search { width: 260px; }
.block__search :deep(.el-input__wrapper) { border-radius: 20px; background: var(--zt-surface-subtle); box-shadow: 0 0 0 1px var(--zt-border) inset; }
.block__search :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1.5px var(--zt-blue-600) inset; background: var(--zt-panel); }
.block__notice { margin-bottom: 0; }
.muted { color: var(--zt-ink-500); font-size: 13px; }

.perm-table-wrap { width: 100%; overflow-x: auto; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); }
.perm-table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
.perm-table thead th { background: var(--zt-surface-subtle); color: var(--zt-ink-700); font-weight: 650; font-size: 12px; padding: 10px 16px; border-bottom: 1px solid var(--zt-border); white-space: nowrap; letter-spacing: 0.2px; }
.col-module { width: 220px; }
.col-level { width: 110px; }
.col-source { min-width: 220px; }
.col-mech { width: 120px; }

.group-row td { background: var(--zt-surface-subtle); padding: 8px 16px; border-top: 1px solid var(--zt-border); border-bottom: 1px solid var(--zt-divider); }
.group-label { display: flex; align-items: center; gap: 8px; }
.group-bar { width: 3px; height: 12px; background: var(--zt-blue-600); border-radius: 2px; }
.group-name { font-size: 12.5px; font-weight: 650; color: var(--zt-ink-900); }
.group-count { font-size: 11.5px; color: var(--zt-ink-500); background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 10px; padding: 0 6px; }

.data-row td { padding: 11px 16px; border-bottom: 1px solid var(--zt-divider); vertical-align: middle; background: var(--zt-panel); transition: background 0.15s ease; }
.data-row:hover td { background: var(--zt-surface-subtle); }
.data-row.is-disabled td { background: var(--zt-panel); }
.data-row.is-disabled .module-title { color: var(--zt-ink-400); }

.module-title { font-weight: 550; color: var(--zt-ink-900); line-height: 1.3; }
.module-code { font-family: var(--zt-font-mono, monospace); font-size: 11.5px; color: var(--zt-ink-400); margin-top: 2px; }

.perm-pill { display: inline-flex; align-items: center; gap: 5px; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.perm-pill--full { background: var(--zt-success-soft); color: var(--zt-success-text); border: 1px solid var(--zt-success-border); }
.perm-pill--read { background: var(--el-color-primary-light-9); color: var(--zt-blue-600); border: 1px solid var(--el-color-primary-light-7); }
.perm-pill--none { background: var(--zt-surface-subtle); color: var(--zt-ink-400); border: 1px solid var(--zt-border); }
.pill-dot { width: 6px; height: 6px; border-radius: 50%; }
.pill-dot.is-full { background: var(--zt-success); }
.pill-dot.is-read { background: var(--zt-blue-600); }
.pill-dot.is-none { background: var(--zt-muted-mark); }

.source-list { display: flex; flex-wrap: wrap; gap: 6px; }
.source-badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; background: var(--zt-surface-subtle); border: 1px solid var(--zt-border); border-radius: 12px; font-size: 12px; color: var(--zt-ink-900); }
.source-badge--direct { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-7); color: var(--zt-blue-600); }
.source-badge--inactive { opacity: 0.6; text-decoration: line-through; }
.source-badge__level { color: var(--zt-ink-500); font-size: 11.5px; }
.source-empty { color: var(--zt-ink-400); font-size: 12px; }

.mech-item { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; }
.mech-dot { width: 6px; height: 6px; border-radius: 50%; }
.mech-warn { color: var(--zt-warning-text); }
.mech-warn .mech-dot { background: var(--zt-warning-text); }
.mech-direct { color: var(--zt-blue-700); font-weight: 500; }
.mech-direct .mech-dot { background: var(--zt-blue-600); }
.mech-inherit { color: var(--zt-ink-700); }
.mech-inherit .mech-dot { background: var(--zt-ink-400); }
.mech-none { color: var(--zt-ink-400); }
</style>
