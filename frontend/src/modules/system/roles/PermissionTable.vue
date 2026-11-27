<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ArrowDown, ArrowRight, Lock } from '@element-plus/icons-vue'

import { LEVEL_TEXT, lockReason, writesHint, type ModuleEntry, type ModuleGroup } from '@/permissions/catalog'
import type { GrantLevel } from '@/permissions/levels'
import {
  COLUMNS,
  columnState as groupColumnState,
  countChangedModules,
  countOpenedModules,
  countTotalModules,
  filterCapabilities,
  filterGroupsByStatus,
  isChanged,
  isLocked,
  levelOf as grantLevel,
  openedCount as groupOpenedCount,
  toggleCell,
  toggleGroupColumn,
  type Column,
  type PermissionStatusFilter,
} from '@/permissions/matrix'
import PermissionCells from './PermissionCells.vue'
import PermissionTableHeader from './PermissionTableHeader.vue'

/**
 * 角色权限矩阵：零漏缝吸顶表头 + 十字列高亮 + 分组折叠 + 快捷状态筛选 + 整格热区勾选。
 * 勾「管理」自动带上前两列，取消「查看」整行清空。纯规则在 permissions/matrix.ts。
 */
const props = defineProps<{
  groups: ModuleGroup[]
  modelValue: Record<string, GrantLevel>
  original: Record<string, GrantLevel>
  disabled: boolean
  roleCode?: string
  capabilities?: ModuleEntry[]
  scopeBadges?: Record<string, string>
}>()
const emit = defineEmits<{
  'update:modelValue': [value: Record<string, GrantLevel>]
  openScope: [code: string]
}>()

const keyword = ref('')
const statusFilter = ref<PermissionStatusFilter>('ALL')
const hoveredCol = ref<Column | null>(null)
const collapsed = reactive<Record<string, boolean>>({})
const isStuck = ref(false)
const sentinelRef = ref<HTMLElement | null>(null)

const visibleGroups = computed(() =>
  filterGroupsByStatus(props.groups, props.modelValue, props.original, keyword.value, statusFilter.value),
)
const visibleCapabilities = computed(() => {
  if (statusFilter.value !== 'ALL') return []
  return filterCapabilities(props.capabilities ?? [], keyword.value)
})
const totalModules = computed(() => countTotalModules(props.groups))
const totalOpened = computed(() => countOpenedModules(props.groups, props.modelValue))
const totalChanged = computed(() => countChangedModules(props.groups, props.modelValue, props.original))
const allCollapsed = computed(
  () => visibleGroups.value.length > 0 && visibleGroups.value.every(group => collapsed[group.code]),
)

const levelOf = (code: string) => grantLevel(props.modelValue, code)
const changed = (code: string) => isChanged(props.modelValue, props.original, code)
const locked = (module: ModuleEntry) => isLocked(module, props.roleCode)
const openedCount = (group: ModuleGroup) => groupOpenedCount(group, props.modelValue)
const columnState = (group: ModuleGroup, column: Column) =>
  groupColumnState(group, column, props.modelValue, props.roleCode)
const isGroupCollapsed = (code: string) => Boolean(collapsed[code]) && !keyword.value.trim()

function capabilityHint(module: ModuleEntry): string {
  return locked(module) ? lockReason(module.code, props.roleCode) : '能给人分配角色，也能修改角色权限'
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

function toggleGroup(code: string) {
  collapsed[code] = !collapsed[code]
}

function toggleAllGroups() {
  const nextState = !allCollapsed.value
  for (const group of visibleGroups.value) collapsed[group.code] = nextState
}

async function jumpToGroup(code: string) {
  if (statusFilter.value !== 'ALL' || keyword.value) {
    statusFilter.value = 'ALL'
    keyword.value = ''
  }
  collapsed[code] = false
  await nextTick()
  document.getElementById(`perm-group-${code}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

let observer: IntersectionObserver | null = null
onMounted(() => {
  if (typeof IntersectionObserver === 'undefined' || !sentinelRef.value) return
  observer = new IntersectionObserver(
    entries => {
      const entry = entries[0]
      if (entry) isStuck.value = !entry.isIntersecting
    },
    { threshold: 0 },
  )
  observer.observe(sentinelRef.value)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <div class="perm-menu">
    <div
      ref="sentinelRef"
      class="perm-sticky-sentinel"
      aria-hidden="true"
    />
    <PermissionTableHeader
      v-model:keyword="keyword"
      v-model:status-filter="statusFilter"
      :groups="groups"
      :grants="modelValue"
      :total-modules="totalModules"
      :total-opened="totalOpened"
      :total-changed="totalChanged"
      :all-collapsed="allCollapsed"
      :hovered-col="hoveredCol"
      :is-stuck="isStuck"
      @toggle-all="toggleAllGroups"
      @jump-group="jumpToGroup"
    />

    <p
      v-if="!visibleGroups.length && !visibleCapabilities.length"
      class="perm-menu__empty"
    >
      {{ keyword || statusFilter !== 'ALL' ? '当前筛选条件下没有匹配的菜单' : '暂无可配置的菜单权限' }}
    </p>

    <div
      v-else
      class="perm-rows-body"
      role="table"
      aria-label="菜单权限矩阵"
    >
      <section
        v-for="group in visibleGroups"
        :id="`perm-group-${group.code}`"
        :key="group.code"
        class="perm-group"
        :class="{ 'is-collapsed': isGroupCollapsed(group.code) }"
      >
        <div class="perm-group__head perm-grid-cols">
          <button
            type="button"
            class="perm-group__toggle"
            :aria-expanded="!isGroupCollapsed(group.code)"
            @click="toggleGroup(group.code)"
          >
            <el-icon
              class="perm-group__chev"
              aria-hidden="true"
            >
              <ArrowDown />
            </el-icon>
            <span class="perm-group__name">{{ group.name }}</span>
            <span
              class="perm-group__count"
              :class="{ 'is-some': openedCount(group) > 0 }"
            >
              已开通 {{ openedCount(group) }} / {{ group.modules.length }}
            </span>
          </button>

          <template
            v-for="column in COLUMNS"
            :key="column.level"
          >
            <label
              v-if="!columnState(group, column.level).empty"
              class="perm-cell"
              :class="{ 'is-disabled': disabled }"
              :title="`${group.name}整组${column.label}`"
              @mouseenter="hoveredCol = column.level"
              @mouseleave="hoveredCol = null"
            >
              <input
                type="checkbox"
                :aria-label="`${group.name}整组${column.label}`"
                :checked="columnState(group, column.level).checked"
                :indeterminate="columnState(group, column.level).indeterminate"
                :disabled="disabled"
                @change="onColumn(group, column.level)"
              >
            </label>
            <div
              v-else
              class="perm-cell is-na"
              @mouseenter="hoveredCol = column.level"
              @mouseleave="hoveredCol = null"
            >
              <span class="perm-matrix__na">—</span>
            </div>
          </template>

          <div class="perm-group__note">
            {{ isGroupCollapsed(group.code) ? '点击左侧展开该分组' : '勾本行复选框可一次全选整列' }}
          </div>
        </div>

        <template v-if="!isGroupCollapsed(group.code)">
          <div
            v-for="module in group.modules"
            :key="module.code"
            class="perm-row perm-table__row perm-grid-cols"
            :class="{ 'is-on': levelOf(module.code) !== 'NONE', 'is-changed': changed(module.code) }"
            role="row"
          >
            <div class="perm-row__name">
              <span class="perm-row__label">{{ module.name }}</span>
              <span
                v-if="levelOf(module.code) !== 'NONE'"
                class="perm-level-pill"
                :class="`is-${levelOf(module.code).toLowerCase()}`"
              >
                {{ LEVEL_TEXT[levelOf(module.code)] }}
              </span>
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
              <button
                v-if="scopeBadges?.[module.code]"
                type="button"
                class="perm-scope-chip"
                title="点击前往「智库数据权限」精细配置范围"
                @click="emit('openScope', module.code)"
              >
                <span>{{ scopeBadges[module.code] }}</span>
                <el-icon :size="11">
                  <ArrowRight />
                </el-icon>
              </button>
            </div>
            <PermissionCells
              :module="module"
              :level="levelOf(module.code)"
              :disabled="disabled || locked(module)"
              @toggle="onCell(module, $event)"
              @hover-col="hoveredCol = $event"
            />
            <div class="perm-row__hint">
              {{ writesHint(module) }}
            </div>
          </div>
        </template>
      </section>

      <section
        v-if="visibleCapabilities.length"
        class="perm-group perm-capability"
      >
        <div class="perm-group__head perm-grid-cols">
          <div class="perm-group__toggle is-static">
            <span class="perm-group__name">特殊能力</span>
            <span class="perm-group__count">仅超管</span>
          </div>
          <div /><div /><div />
          <div class="perm-group__note">
            不是菜单。只属于超级管理员，防止有人给自己加权限。
          </div>
        </div>
        <div
          v-for="module in visibleCapabilities"
          :key="module.code"
          class="perm-row perm-table__row perm-grid-cols"
          :class="{ 'is-on': levelOf(module.code) !== 'NONE', 'is-changed': changed(module.code) }"
          role="row"
        >
          <div class="perm-row__name">
            <span class="perm-row__label">{{ module.name }}</span>
            <el-icon
              v-if="locked(module)"
              class="perm-row__lock"
              aria-hidden="true"
            >
              <Lock />
            </el-icon>
            <span
              v-if="levelOf(module.code) !== 'NONE'"
              class="perm-level-pill"
              :class="`is-${levelOf(module.code).toLowerCase()}`"
            >
              {{ LEVEL_TEXT[levelOf(module.code)] }}
            </span>
          </div>
          <PermissionCells
            :module="module"
            :level="levelOf(module.code)"
            :disabled="disabled || locked(module)"
            @toggle="onCell(module, $event)"
            @hover-col="hoveredCol = $event"
          />
          <div class="perm-row__hint">
            {{ capabilityHint(module) }}
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped src="./permission-table.css"></style>
