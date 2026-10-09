<script setup lang="ts">
import { computed, ref } from 'vue'
import { Lock, Search } from '@element-plus/icons-vue'

import {
  levelHint,
  lockReason,
  writesHint,
  type ModuleEntry,
  type ModuleGroup,
} from '@/permissions/catalog'
import type { GrantLevel } from '@/permissions/levels'

/**
 * 角色权限：按菜单分组纵向列出，一项只选一档。
 * 档位逐档包含，选「导出」已经包含查看，选「管理」已经包含查看和导出。
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

const LEVEL_SHORT: Record<GrantLevel, string> = {
  NONE: '不开放',
  READ: '查看',
  EXPORT: '导出',
  FULL: '管理',
}

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
  const level = levelOf(module.code)
  if (locked(module)) return lockReason(module.code, props.roleCode)
  if (level === 'NONE') return '不能给人分配角色，也不能修改权限'
  if (level === 'READ') return '只能查看权限设置，不能修改'
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

function highest(module: ModuleEntry): GrantLevel {
  return module.levels[module.levels.length - 1] ?? 'NONE'
}

function openedCount(group: ModuleGroup): number {
  return group.modules.filter(module => levelOf(module.code) !== 'NONE').length
}

function groupTargets(group: ModuleGroup): ModuleEntry[] {
  return group.modules.filter(module => !locked(module))
}

function groupState(group: ModuleGroup): { checked: boolean; indeterminate: boolean } {
  const targets = groupTargets(group)
  if (!targets.length) return { checked: false, indeterminate: false }
  const open = targets.filter(module => levelOf(module.code) !== 'NONE').length
  const atMax = targets.filter(module => levelOf(module.code) === highest(module)).length
  return {
    checked: atMax === targets.length,
    indeterminate: open > 0 && atMax < targets.length,
  }
}

function setLevel(module: ModuleEntry, level: GrantLevel) {
  if (props.disabled || locked(module) || !module.levels.includes(level)) return
  emit('update:modelValue', { ...props.modelValue, [module.code]: level })
}

/** 开通整组：没到各自最高档时升到最高档，已经全开时再点一次全部关闭。 */
function toggleGroup(group: ModuleGroup) {
  const targets = groupTargets(group)
  if (props.disabled || !targets.length) return
  const allMax = targets.every(module => levelOf(module.code) === highest(module))
  const next = { ...props.modelValue }
  for (const module of targets) next[module.code] = allMax ? 'NONE' : highest(module)
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
    </div>
    <p
      v-if="!visibleGroups.length && !visibleCapabilities.length"
      class="perm-menu__empty"
    >
      没有匹配的菜单
    </p>
    <section
      v-for="group in visibleGroups"
      :key="group.code"
      class="perm-group"
    >
      <div class="perm-group__head">
        <span class="perm-group__name">{{ group.name }}</span>
        <el-checkbox
          :model-value="groupState(group).checked"
          :indeterminate="groupState(group).indeterminate"
          :disabled="disabled || !groupTargets(group).length"
          @change="toggleGroup(group)"
        >
          开通整组
        </el-checkbox>
        <span class="perm-group__count">已开通 {{ openedCount(group) }} / {{ group.modules.length }}</span>
      </div>
      <div
        v-for="module in group.modules"
        :key="module.code"
        class="perm-row perm-table__row"
        :class="{ 'is-on': levelOf(module.code) !== 'NONE', 'is-changed': changed(module.code) }"
      >
        <div class="perm-row__name">
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
        </div>
        <div
          class="perm-levels"
          role="radiogroup"
          :aria-label="`${module.name}的权限`"
        >
          <label
            v-for="level in module.levels"
            :key="level"
            class="perm-levels__item"
            :class="{
              'is-selected': levelOf(module.code) === level && level !== 'NONE',
              'is-quiet': level === 'NONE' && levelOf(module.code) === 'NONE',
            }"
          >
            <input
              type="radio"
              :name="`grant-${module.code}`"
              :value="level"
              :checked="levelOf(module.code) === level"
              :disabled="disabled || locked(module)"
              @change="setLevel(module, level)"
            >
            <span>{{ LEVEL_SHORT[level] }}</span>
          </label>
        </div>
        <p class="perm-row__hint">
          {{ levelHint(module, levelOf(module.code)) }} · {{ writesHint(module) }}
        </p>
      </div>
    </section>
    <section
      v-if="visibleCapabilities.length"
      class="perm-capability"
    >
      <div class="perm-capability__head">
        <span class="perm-group__name">分配角色</span>
        <span class="perm-capability__note">不是菜单。只有超级管理员能拥有，用来给人分配角色、修改权限。</span>
      </div>
      <div
        v-for="module in visibleCapabilities"
        :key="module.code"
        class="perm-row perm-table__row"
        :class="{ 'is-on': levelOf(module.code) !== 'NONE', 'is-changed': changed(module.code) }"
      >
        <div class="perm-row__name">
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
        </div>
        <div
          class="perm-levels"
          role="radiogroup"
          :aria-label="`${module.name}的权限`"
        >
          <label
            v-for="level in module.levels"
            :key="level"
            class="perm-levels__item"
            :class="{
              'is-selected': levelOf(module.code) === level && level !== 'NONE',
              'is-quiet': level === 'NONE' && levelOf(module.code) === 'NONE',
            }"
          >
            <input
              type="radio"
              :name="`grant-${module.code}`"
              :value="level"
              :checked="levelOf(module.code) === level"
              :disabled="disabled || locked(module)"
              @change="setLevel(module, level)"
            >
            <span>{{ LEVEL_SHORT[level] }}</span>
          </label>
        </div>
        <p class="perm-row__hint">
          {{ capabilityHint(module) }}
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.perm-menu {
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
}

.perm-menu__search {
  padding: 12px 16px;
  border-bottom: 1px solid #eef1f6;
}

.perm-menu__empty {
  margin: 0;
  padding: 28px 16px;
  text-align: center;
  color: var(--zt-ink-500);
}

.perm-group + .perm-group,
.perm-capability {
  border-top: 1px solid var(--zt-border);
}

.perm-capability__head {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 16px;
  padding: 10px 16px;
  background: #fafbfd;
}

.perm-capability__note {
  font-size: 12px;
  line-height: 1.5;
  color: var(--zt-ink-500);
}

.perm-group__head {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  background: #fafbfd;
}

.perm-group__name {
  font-weight: 650;
  color: var(--zt-ink-900);
}

.perm-group__count {
  margin-left: auto;
  font-size: 12px;
  color: var(--zt-ink-500);
  font-variant-numeric: tabular-nums;
}

.perm-row {
  display: grid;
  grid-template-columns: minmax(148px, 200px) auto minmax(180px, 1fr);
  align-items: center;
  gap: 8px 16px;
  padding: 10px 16px 10px 28px;
  border-top: 1px solid #eef1f6;
}

.perm-row:hover {
  background: #f7faff;
}

.perm-row.is-changed {
  background: #fffaf0;
}

.perm-row:not(.is-on) .perm-row__name {
  color: var(--zt-ink-700);
}

.perm-row__name {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: var(--zt-ink-900);
}

.perm-row__lock {
  color: var(--zt-ink-500);
}

.perm-row__changed {
  flex: none;
  padding: 0 6px;
  border-radius: 10px;
  background: #fdf0d5;
  font-size: 12px;
  line-height: 18px;
  color: #9a702d;
}

.perm-levels {
  display: inline-flex;
  border: 1px solid var(--zt-border);
  border-radius: 6px;
  overflow: hidden;
  background: #fff;
}

.perm-levels__item {
  position: relative;
  display: inline-flex;
  margin: 0;
  cursor: pointer;
  border-left: 1px solid var(--zt-border);
  color: var(--zt-ink-700);
  font-size: 13px;
  line-height: 1;
}

.perm-levels__item:first-child {
  border-left: 0;
}

.perm-levels__item span {
  padding: 6px 12px;
}

.perm-levels__item input {
  position: absolute;
  opacity: 0;
  inset: 0;
  margin: 0;
  cursor: inherit;
}

.perm-levels__item.is-selected {
  background: #eef1fc;
  color: #3558de;
  font-weight: 650;
}

/* 没开通时不给「不开放」上色，避免整页都是蓝色选中态。 */
.perm-levels__item.is-quiet {
  background: transparent;
  color: var(--zt-ink-500);
  font-weight: 400;
}

.perm-levels__item:has(input:disabled) {
  cursor: not-allowed;
  color: #c0c6d0;
}

.perm-levels__item.is-selected:has(input:disabled) {
  background: #f4f6fb;
  color: #8b95a8;
}

.perm-levels__item:focus-within {
  outline: 2px solid #3558de;
  outline-offset: -2px;
  z-index: 1;
}

.perm-row__hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--zt-ink-500);
}

@media (max-width: 960px) {
  .perm-row {
    grid-template-columns: 1fr;
    padding-left: 16px;
  }
}
</style>
