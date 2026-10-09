<script setup lang="ts">
import { computed, ref } from 'vue'
import { Lock, Search } from '@element-plus/icons-vue'

import {
  isChecked,
  lockReason,
  supports,
  toggleColumn,
  writesHint,
  type ModuleEntry,
  type ModuleGroup,
} from '@/permissions/catalog'
import type { GrantLevel } from '@/permissions/levels'

/**
 * 角色权限矩阵：行是菜单，列是查看 / 导出 / 管理，和常见后台的勾选习惯一致。
 * 存下来的仍是一个档位（逐档包含）：勾「管理」自动带上前两列，取消「查看」整行清空。
 */
const props = defineProps<{
  groups: ModuleGroup[]
  modelValue: Record<string, GrantLevel>
  original: Record<string, GrantLevel>
  disabled: boolean
  roleCode?: string
  capabilities?: ModuleEntry[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, GrantLevel>] }>()

type Column = Exclude<GrantLevel, 'NONE'>
const COLUMNS: { level: Column; label: string; what: string }[] = [
  { level: 'READ', label: '查看', what: '打开菜单，看列表和详情' },
  { level: 'EXPORT', label: '导出', what: '下载 Excel' },
  { level: 'FULL', label: '管理', what: '新增、编辑、导入等' },
]

const keyword = ref('')

const visibleGroups = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) return props.groups
  return props.groups.flatMap(group => {
    if (group.name.toLowerCase().includes(query)) return [group]
    const modules = group.modules.filter(module =>
      module.name.toLowerCase().includes(query) || module.code.toLowerCase().includes(query))
    return modules.length ? [{ ...group, modules }] : []
  })
})

const visibleCapabilities = computed(() => {
  const items = props.capabilities ?? []
  const query = keyword.value.trim().toLowerCase()
  if (!query) return items
  return items.filter(module => `${module.name} ${module.code} 分配角色 权限`.toLowerCase().includes(query))
})

function capabilityHint(module: ModuleEntry): string {
  if (locked(module)) return lockReason(module.code, props.roleCode)
  return '能给人分配角色，也能修改角色权限'
}

function levelOf(code: string): GrantLevel {
  return props.modelValue[code] ?? 'NONE'
}

function changed(code: string): boolean {
  return levelOf(code) !== (props.original[code] ?? 'NONE')
}

function locked(module: ModuleEntry): boolean {
  return !!lockReason(module.code, props.roleCode)
}

function openedCount(group: ModuleGroup): number {
  return group.modules.filter(module => levelOf(module.code) !== 'NONE').length
}

function onCell(module: ModuleEntry, column: Column) {
  if (props.disabled || locked(module) || !supports(module, column)) return
  emit('update:modelValue', { ...props.modelValue, [module.code]: toggleColumn(module, levelOf(module.code), column) })
}

function columnTargets(group: ModuleGroup, column: Column): ModuleEntry[] {
  return group.modules.filter(module => !locked(module) && supports(module, column))
}

function columnState(group: ModuleGroup, column: Column): { checked: boolean; indeterminate: boolean; empty: boolean } {
  const targets = columnTargets(group, column)
  const on = targets.filter(module => isChecked(levelOf(module.code), column)).length
  return { checked: targets.length > 0 && on === targets.length, indeterminate: on > 0 && on < targets.length, empty: !targets.length }
}

/** 整组一列：没勾满就全部勾上（已有更高档的保留），已勾满再点一次全部取消这一列。 */
function onColumn(group: ModuleGroup, column: Column) {
  const targets = columnTargets(group, column)
  if (props.disabled || !targets.length) return
  const allOn = targets.every(module => isChecked(levelOf(module.code), column))
  const next = { ...props.modelValue }
  for (const module of targets) {
    const current = levelOf(module.code)
    if (allOn || !isChecked(current, column)) next[module.code] = toggleColumn(module, current, column)
  }
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="perm-menu">
    <div class="perm-menu__search">
      <el-input
        v-model="keyword"
        clearable
        placeholder="搜索菜单，例如省市区"
        aria-label="搜索菜单"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <p class="perm-legend">
        <span
          v-for="column in COLUMNS"
          :key="column.level"
        ><b>{{ column.label }}</b>：{{ column.what }}</span>
        <span>勾「管理」会自动带上「查看」「导出」</span>
      </p>
    </div>
    <p
      v-if="!visibleGroups.length && !visibleCapabilities.length"
      class="perm-menu__empty"
    >
      没有匹配的菜单
    </p>
    <div
      v-else
      class="perm-scroll"
    >
      <table class="perm-matrix">
        <thead>
          <tr>
            <th scope="col">
              菜单
            </th>
            <th
              v-for="column in COLUMNS"
              :key="column.level"
              scope="col"
              class="perm-matrix__col"
            >
              {{ column.label }}
            </th>
            <th scope="col">
              「管理」包含
            </th>
          </tr>
        </thead>
        <tbody
          v-for="group in visibleGroups"
          :key="group.code"
          class="perm-group"
        >
          <tr class="perm-group__head">
            <th scope="rowgroup">
              <span class="perm-group__name">{{ group.name }}</span>
              <span class="perm-group__count">已开通 {{ openedCount(group) }} / {{ group.modules.length }}</span>
            </th>
            <td
              v-for="column in COLUMNS"
              :key="column.level"
              class="perm-matrix__col"
            >
              <input
                v-if="!columnState(group, column.level).empty"
                type="checkbox"
                :aria-label="`${group.name}整组${column.label}`"
                :checked="columnState(group, column.level).checked"
                :indeterminate="columnState(group, column.level).indeterminate"
                :disabled="disabled"
                @change="onColumn(group, column.level)"
              >
            </td>
            <td />
          </tr>
          <tr
            v-for="module in group.modules"
            :key="module.code"
            class="perm-row perm-table__row"
            :class="{ 'is-on': levelOf(module.code) !== 'NONE', 'is-changed': changed(module.code) }"
          >
            <th
              scope="row"
              class="perm-row__name"
            >
              <span>{{ module.name }}</span>
              <el-tooltip
                v-if="locked(module)"
                :content="lockReason(module.code, roleCode)"
                placement="top"
              >
                <el-icon
                  class="perm-row__lock"
                  aria-hidden="true"
                >
                  <Lock />
                </el-icon>
              </el-tooltip>
              <span
                v-if="changed(module.code)"
                class="perm-row__changed"
              >已修改</span>
            </th>
            <td
              v-for="column in COLUMNS"
              :key="column.level"
              class="perm-matrix__col"
            >
              <input
                v-if="supports(module, column.level)"
                type="checkbox"
                :aria-label="`${module.name} ${column.label}`"
                :checked="isChecked(levelOf(module.code), column.level)"
                :disabled="disabled || locked(module)"
                @change="onCell(module, column.level)"
              >
              <span
                v-else
                class="perm-matrix__na"
                title="这个菜单没有这项操作"
              >—</span>
            </td>
            <td class="perm-row__hint">
              {{ writesHint(module) }}
            </td>
          </tr>
        </tbody>
        <tbody
          v-if="visibleCapabilities.length"
          class="perm-capability"
        >
          <tr class="perm-group__head">
            <th
              scope="rowgroup"
              colspan="5"
            >
              <span class="perm-group__name">特殊能力</span>
              <span class="perm-capability__note">不是菜单。只属于超级管理员，防止有人给自己加权限。</span>
            </th>
          </tr>
          <tr
            v-for="module in visibleCapabilities"
            :key="module.code"
            class="perm-row perm-table__row"
            :class="{ 'is-on': levelOf(module.code) !== 'NONE', 'is-changed': changed(module.code) }"
          >
            <th
              scope="row"
              class="perm-row__name"
            >
              <span>{{ module.name }}</span>
              <el-icon
                v-if="locked(module)"
                class="perm-row__lock"
                aria-hidden="true"
              >
                <Lock />
              </el-icon>
            </th>
            <td
              v-for="column in COLUMNS"
              :key="column.level"
              class="perm-matrix__col"
            >
              <input
                v-if="supports(module, column.level)"
                type="checkbox"
                :aria-label="`${module.name} ${column.label}`"
                :checked="isChecked(levelOf(module.code), column.level)"
                :disabled="disabled || locked(module)"
                @change="onCell(module, column.level)"
              >
              <span
                v-else
                class="perm-matrix__na"
              >—</span>
            </td>
            <td class="perm-row__hint">
              {{ capabilityHint(module) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.perm-menu {
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
}

.perm-menu__search {
  display: grid;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #eef1f6;
}

.perm-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 20px;
  margin: 0;
  font-size: 12px;
  color: var(--zt-ink-500);
}

.perm-legend b {
  font-weight: 600;
  color: var(--zt-ink-700);
}

.perm-menu__empty {
  margin: 0;
  padding: 28px 16px;
  text-align: center;
  color: var(--zt-ink-500);
}

.perm-scroll {
  overflow-x: auto;
}

.perm-matrix {
  width: 100%;
  min-width: 640px;
  border-collapse: collapse;
}

.perm-matrix th,
.perm-matrix td {
  padding: 9px 16px;
  border-top: 1px solid #eef1f6;
  text-align: left;
  font-weight: 400;
  vertical-align: middle;
}

.perm-matrix thead th {
  border-top: 0;
  background: var(--zt-soft);
  font-size: 13px;
  color: var(--zt-ink-500);
}

.perm-matrix .perm-matrix__col {
  width: 76px;
  text-align: center;
}

.perm-matrix input[type="checkbox"] {
  width: 16px;
  height: 16px;
  margin: 0;
  vertical-align: middle;
  accent-color: #3558de;
  cursor: pointer;
}

.perm-matrix input[type="checkbox"]:disabled {
  cursor: not-allowed;
}

.perm-matrix__na {
  color: #c0c6d0;
}

.perm-group__head th,
.perm-group__head td {
  border-top: 1px solid var(--zt-border);
  background: #fafbfd;
}

.perm-group__name {
  font-weight: 650;
  color: var(--zt-ink-900);
}

.perm-group__count,
.perm-capability__note {
  margin-left: 12px;
  font-size: 12px;
  color: var(--zt-ink-500);
  font-variant-numeric: tabular-nums;
}

.perm-row:hover {
  background: #f7faff;
}

.perm-row.is-changed {
  background: #fffaf0;
}

.perm-matrix .perm-row__name {
  padding-left: 28px;
  color: var(--zt-ink-900);
  white-space: nowrap;
}

.perm-row:not(.is-on) .perm-row__name {
  color: var(--zt-ink-700);
}

.perm-row__name > * + * {
  margin-left: 6px;
}

.perm-row__lock {
  vertical-align: -2px;
  color: var(--zt-ink-500);
}

.perm-row__changed {
  padding: 0 6px;
  border-radius: 10px;
  background: #fdf0d5;
  font-size: 12px;
  line-height: 18px;
  color: #9a702d;
}

.perm-matrix .perm-row__hint {
  font-size: 12px;
  line-height: 1.5;
  color: var(--zt-ink-500);
}
</style>
