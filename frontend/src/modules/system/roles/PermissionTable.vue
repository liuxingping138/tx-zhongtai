<script setup lang="ts">
import { computed, ref } from 'vue'
import { Lock, Search } from '@element-plus/icons-vue'

import { lockReason, writesHint, type ModuleEntry, type ModuleGroup } from '@/permissions/catalog'
import type { GrantLevel } from '@/permissions/levels'
import {
  COLUMNS,
  columnState as groupColumnState,
  filterCapabilities,
  filterGroups,
  isChanged,
  isLocked,
  levelOf as grantLevel,
  openedCount as groupOpenedCount,
  toggleCell,
  toggleGroupColumn,
  type Column,
} from '@/permissions/matrix'
import PermissionCells from './PermissionCells.vue'

/**
 * 角色权限矩阵：行是菜单，列是查看 / 导出 / 管理，和常见后台的勾选习惯一致。
 * 存下来的仍是一个档位（逐档包含）：勾「管理」自动带上前两列，取消「查看」整行清空。
 * 勾选规则在 permissions/matrix.ts，这里只负责渲染和把结果抛给父组件。
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

const keyword = ref('')
const visibleGroups = computed(() => filterGroups(props.groups, keyword.value))
const visibleCapabilities = computed(() => filterCapabilities(props.capabilities ?? [], keyword.value))

const levelOf = (code: string) => grantLevel(props.modelValue, code)
const changed = (code: string) => isChanged(props.modelValue, props.original, code)
const locked = (module: ModuleEntry) => isLocked(module, props.roleCode)
const openedCount = (group: ModuleGroup) => groupOpenedCount(group, props.modelValue)
const columnState = (group: ModuleGroup, column: Column) => groupColumnState(group, column, props.modelValue, props.roleCode)

function capabilityHint(module: ModuleEntry): string {
  if (locked(module)) return lockReason(module.code, props.roleCode)
  return '能给人分配角色，也能修改角色权限'
}

function onCell(module: ModuleEntry, column: Column) {
  if (props.disabled) return
  const next = toggleCell(module, column, props.modelValue, props.roleCode)
  if (next) emit('update:modelValue', next)
}

function onColumn(group: ModuleGroup, column: Column) {
  if (props.disabled) return
  const next = toggleGroupColumn(group, column, props.modelValue, props.roleCode)
  if (next) emit('update:modelValue', next)
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
            <PermissionCells
              :module="module"
              :level="levelOf(module.code)"
              :disabled="disabled || locked(module)"
              @toggle="onCell(module, $event)"
            />
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
            <PermissionCells
              :module="module"
              :level="levelOf(module.code)"
              :disabled="disabled || locked(module)"
              @toggle="onCell(module, $event)"
            />
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
  /* 1200px 宽的屏幕上详情区只有约 590px，最小宽度再大会把「管理包含」列裁到横向滚动里。 */
  min-width: 520px;
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

/* 格子在子组件 PermissionCells 里渲染，作用域样式要用 :deep 才够得到。 */
.perm-matrix :deep(.perm-matrix__col) {
  width: 76px;
  text-align: center;
}

.perm-matrix :deep(input[type="checkbox"]) {
  width: 16px;
  height: 16px;
  margin: 0;
  vertical-align: middle;
  accent-color: #3558de;
  cursor: pointer;
}

.perm-matrix :deep(input[type="checkbox"]:disabled) {
  cursor: not-allowed;
}

.perm-matrix :deep(.perm-matrix__na) {
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

/* 「已开通 4 / 4」固定放在分组名下一行：放同一行时会随列宽时而同行、时而折行，
   各分组对不齐；整体不换行，不把「/ 4」拆开。 */
.perm-group__count {
  display: block;
  margin-left: 0;
  white-space: nowrap;
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
