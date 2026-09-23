<script setup lang="ts">
import { computed } from 'vue'
import { InfoFilled, Lock } from '@element-plus/icons-vue'

import {
  isChecked,
  lockReason,
  PERMISSION_COLUMNS,
  rank,
  supports,
  toggleColumn,
  writesHint,
  type ModuleEntry,
  type ModuleGroup,
} from '@/permissions/catalog'
import type { GrantLevel } from '@/permissions/levels'

/**
 * 角色权限表：行是模块，列是「查看 / 导出 / 管理」，勾选即授权（参考 Strapi、Directus 的角色权限矩阵）。
 * 档位逐档包含，所以勾后面的列自动勾上前面的列。
 */
const props = defineProps<{
  groups: ModuleGroup[]
  modelValue: Record<string, GrantLevel>
  original: Record<string, GrantLevel>
  disabled: boolean
  roleCode?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, GrantLevel>] }>()

const allModules = computed(() => props.groups.flatMap(group => group.modules))

function levelOf(code: string): GrantLevel {
  return props.modelValue[code] ?? 'NONE'
}

function changed(code: string): boolean {
  return levelOf(code) !== (props.original[code] ?? 'NONE')
}

function locked(module: ModuleEntry): boolean {
  return !!lockReason(module.code, props.roleCode)
}

function editable(modules: ModuleEntry[], column: GrantLevel): ModuleEntry[] {
  return modules.filter(module => supports(module, column) && !locked(module))
}

function toggleCell(module: ModuleEntry, column: GrantLevel) {
  emit('update:modelValue', { ...props.modelValue, [module.code]: toggleColumn(module, levelOf(module.code), column) })
}

/** 整列 / 整组勾选：全部已勾时取消，否则全部勾上。 */
function toggleMany(modules: ModuleEntry[], column: GrantLevel) {
  const targets = editable(modules, column)
  if (!targets.length) return
  const allOn = targets.every(module => isChecked(levelOf(module.code), column))
  const next = { ...props.modelValue }
  for (const module of targets) {
    const current = levelOf(module.code)
    if (allOn) next[module.code] = toggleColumn(module, current, column)
    else if (rank(current) < rank(column)) next[module.code] = column
  }
  emit('update:modelValue', next)
}

function state(modules: ModuleEntry[], column: GrantLevel): { checked: boolean; indeterminate: boolean; empty: boolean } {
  const targets = modules.filter(module => supports(module, column))
  if (!targets.length) return { checked: false, indeterminate: false, empty: true }
  const on = targets.filter(module => isChecked(levelOf(module.code), column)).length
  return { checked: on === targets.length, indeterminate: on > 0 && on < targets.length, empty: false }
}

function openedCount(group: ModuleGroup): number {
  return group.modules.filter(module => levelOf(module.code) !== 'NONE').length
}
</script>

<template>
  <div class="perm-table-wrap">
    <table
      class="perm-table"
      aria-label="模块权限"
    >
      <colgroup>
        <col class="perm-table__col-name">
        <col
          v-for="column in PERMISSION_COLUMNS"
          :key="column.level"
          class="perm-table__col-check"
        >
        <col>
      </colgroup>
      <thead>
        <tr>
          <th scope="col">
            模块
          </th>
          <th
            v-for="column in PERMISSION_COLUMNS"
            :key="column.level"
            scope="col"
            class="is-check"
          >
            <div class="perm-table__head">
              <el-checkbox
                v-if="!state(allModules, column.level).empty"
                :model-value="state(allModules, column.level).checked"
                :indeterminate="state(allModules, column.level).indeterminate"
                :disabled="disabled"
                :aria-label="`全部模块${column.title}`"
                @change="toggleMany(allModules, column.level)"
              />
              <span>{{ column.title }}</span>
              <el-tooltip
                :content="column.tip"
                placement="top"
              >
                <el-icon
                  class="perm-table__tip"
                  :aria-label="`${column.title}说明`"
                >
                  <InfoFilled />
                </el-icon>
              </el-tooltip>
            </div>
          </th>
          <th
            scope="col"
            class="perm-table__desc-head"
          >
            说明
          </th>
        </tr>
      </thead>
      <tbody
        v-for="group in groups"
        :key="group.code"
      >
        <tr class="perm-table__group">
          <th scope="rowgroup">
            <span class="perm-table__group-name">{{ group.name }}</span>
            <span class="perm-table__group-count">已开通 {{ openedCount(group) }} / {{ group.modules.length }}</span>
          </th>
          <td
            v-for="column in PERMISSION_COLUMNS"
            :key="column.level"
            class="is-check"
          >
            <el-checkbox
              v-if="!state(group.modules, column.level).empty"
              :model-value="state(group.modules, column.level).checked"
              :indeterminate="state(group.modules, column.level).indeterminate"
              :disabled="disabled || !editable(group.modules, column.level).length"
              :aria-label="`${group.name}全部${column.title}`"
              @change="toggleMany(group.modules, column.level)"
            />
          </td>
          <td class="perm-table__desc">
            整组勾选
          </td>
        </tr>
        <tr
          v-for="module in group.modules"
          :key="module.code"
          class="perm-table__row"
          :class="{ 'is-changed': changed(module.code), 'is-on': levelOf(module.code) !== 'NONE' }"
        >
          <th scope="row">
            <span class="perm-table__name">
              {{ module.name }}
              <el-tooltip
                v-if="locked(module)"
                :content="lockReason(module.code, roleCode)"
                placement="top"
              >
                <el-icon
                  class="perm-table__lock"
                  aria-label="已锁定"
                ><Lock /></el-icon>
              </el-tooltip>
              <span
                v-if="changed(module.code)"
                class="perm-table__changed"
              >已修改</span>
            </span>
          </th>
          <td
            v-for="column in PERMISSION_COLUMNS"
            :key="column.level"
            class="is-check"
          >
            <el-checkbox
              v-if="supports(module, column.level)"
              :model-value="isChecked(levelOf(module.code), column.level)"
              :disabled="disabled || locked(module)"
              :aria-label="`${module.name}${column.title}`"
              @change="toggleCell(module, column.level)"
            />
            <span
              v-else
              class="perm-table__na"
              :title="`${module.name}没有${column.title}操作`"
            >—</span>
          </td>
          <td class="perm-table__desc">
            {{ locked(module) ? lockReason(module.code, roleCode) : writesHint(module) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.perm-table-wrap { overflow-x: auto; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); }
.perm-table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 14px; }
.perm-table__col-name { width: 220px; }
.perm-table__col-check { width: 96px; }
.perm-table th, .perm-table td { padding: 10px 16px; border-bottom: 1px solid #eef1f6; text-align: left; font-weight: 400; color: var(--zt-ink-900); }
.perm-table .is-check { text-align: center; padding-left: 8px; padding-right: 8px; }
.perm-table thead th {
  position: sticky; top: 0; z-index: 1; background: #f7f9fc; font-size: 13px; font-weight: 600;
  color: var(--zt-ink-700); border-bottom: 1px solid var(--zt-border);
}
.perm-table__head { display: inline-flex; align-items: center; gap: 6px; }
.perm-table__tip { color: var(--zt-ink-500); cursor: help; }
.perm-table__desc-head { color: var(--zt-ink-500); }
.perm-table__group th, .perm-table__group td { background: #fafbfd; border-top: 1px solid var(--zt-border); }
.perm-table tbody:first-of-type .perm-table__group th,
.perm-table tbody:first-of-type .perm-table__group td { border-top: none; }
.perm-table__group-name { font-weight: 650; color: var(--zt-ink-900); }
.perm-table__group-count { margin-left: 10px; font-size: 12px; color: var(--zt-ink-500); font-variant-numeric: tabular-nums; }
.perm-table__group .perm-table__desc { font-size: 12px; }
.perm-table__row th { padding-left: 32px; }
.perm-table__row:hover th, .perm-table__row:hover td { background: #f7faff; }
.perm-table__row:not(.is-on) .perm-table__name { color: var(--zt-ink-700); }
.perm-table__row.is-changed th, .perm-table__row.is-changed td { background: #fffaf0; }
.perm-table__name { display: inline-flex; align-items: center; gap: 6px; }
.perm-table__lock { color: var(--zt-ink-500); }
.perm-table__changed {
  padding: 0 6px; border: 1px solid #f3d19e; border-radius: 4px; background: #fdf6ec;
  font-size: 12px; line-height: 18px; color: #b26a00;
}
.perm-table__na { color: #c0c6d0; }
.perm-table__desc { font-size: 12px; line-height: 1.5; color: var(--zt-ink-500); }
.perm-table :deep(.el-checkbox) { height: auto; }
</style>
