<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { CandidateItem } from '@/api/scenarioCandidates'
import ListEmpty from '@/components/ListEmpty.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
import CandidateExpand from './CandidateExpand.vue'
import DecisionButtons from './DecisionButtons.vue'
import MatchCell from './MatchCell.vue'
import PlaceCell from './PlaceCell.vue'
import { KIND_NEW, PENDING, decisionText, levelTag, type DecisionMode } from './candidates'
import type { useCandidateExtras } from './useCandidateExtras'

/**
 * 新增场景列表：一行一个场景，看清新增场景级别、挂在哪、码表里像它的，就在这一行决定（不再进单个场景的页面）。
 * 点名称或行首箭头展开看依据；展开时才去取这一行的详情和码表上下文。
 */
const props = defineProps<{
  items: CandidateItem[]
  loading: boolean
  filtered: boolean
  status: string
  canDecide: boolean
  canWriteCodebook: boolean
  extras: ReturnType<typeof useCandidateExtras>
  /** 正在准备确认框的那一行和那个决定 */
  busy: { id: string; mode: DecisionMode } | null
  reopeningId?: string
  /** 从别处带过来要直接展开的那一行 */
  focus: string
}>()
const emit = defineEmits<{
  open: [row: CandidateItem, mode: DecisionMode, target?: string[] | null]
  rows: [row: CandidateItem]
  reopen: [row: CandidateItem]
  changed: [ids: string[]]
  selection: [rows: CandidateItem[]]
  reset: []
}>()

const pending = computed(() => props.status === PENDING)
const table = ref<{ toggleRowExpansion: (row: CandidateItem, expanded?: boolean) => void; clearSelection: () => void }>()
const open = ref<string[]>([])
// 带过来的那一行只在第一次出现时展开一次，之后收起、重新载入都不再自动展开
let focused = false
watch(() => [props.focus, props.items] as const, ([focus, items]) => {
  if (focused || !focus || !items.some(row => row.id === focus)) return
  focused = true
  open.value = [focus]
  void props.extras.ensure(focus)
}, { immediate: true })

function expanded(row: CandidateItem, rows: CandidateItem[]) {
  open.value = rows.map(item => item.id)
  if (open.value.includes(row.id)) void props.extras.ensure(row.id)
}
function toggle(row: CandidateItem) {
  table.value?.toggleRowExpansion(row)
}
function rowClass({ row }: { row: CandidateItem }) {
  return open.value.includes(row.id) ? 'is-open' : ''
}

defineExpose({ clearSelection: () => table.value?.clearSelection() })
</script>

<template>
  <TableSkeleton
    v-if="loading && items.length === 0"
    :columns="pending && canDecide ? 7 : 6"
    :has-actions="canDecide"
  />
  <el-table
    v-else
    ref="table"
    class="data-table candidates-table"
    :class="{ 'is-refreshing': loading }"
    :data="items"
    row-key="id"
    :expand-row-keys="open"
    :row-class-name="rowClass"
    @expand-change="expanded"
    @selection-change="emit('selection', $event)"
  >
    <template #empty>
      <ListEmpty
        :loading="loading"
        :filtered="filtered"
        @reset="emit('reset')"
      />
    </template>
    <el-table-column
      v-if="pending && canDecide"
      type="selection"
      width="44"
    />
    <el-table-column
      type="expand"
      width="32"
    >
      <template #default="{ row }">
        <CandidateExpand
          v-if="row.id"
          :candidate="row"
          :extras="extras.get(row.id)"
          :pending="pending"
          :can-merge="canWriteCodebook"
          :can-absorb="canDecide && pending"
          @merge="path => emit('open', row, 'merge', path)"
          @rows="emit('rows', row)"
          @changed="ids => emit('changed', ids)"
        />
      </template>
    </el-table-column>
    <el-table-column
      label="新增场景"
      min-width="170"
    >
      <template #default="{ row }">
        <button
          v-if="row.id"
          type="button"
          class="candidates-table__name"
          :aria-expanded="open.includes(row.id)"
          :title="open.includes(row.id) ? '收起依据' : '展开看依据'"
          @click="toggle(row)"
        >
          {{ row.name }}
        </button>
      </template>
    </el-table-column>
    <el-table-column
      label="新增场景级别"
      width="116"
    >
      <template #default="{ row }">
        <span :class="['candidates-table__level', { 'candidates-table__level--link': row.kind && row.kind !== KIND_NEW }]">{{ levelTag(row) }}</span>
      </template>
    </el-table-column>
    <el-table-column
      label="挂在哪"
      min-width="180"
    >
      <template #default="{ row }">
        <PlaceCell
          v-if="row.id"
          :candidate="row"
        />
      </template>
    </el-table-column>
    <el-table-column
      v-if="pending"
      label="码表里像它的"
      min-width="250"
    >
      <template #default="{ row }">
        <MatchCell
          v-if="row.id"
          :candidate="row"
        />
      </template>
    </el-table-column>
    <el-table-column
      v-else
      label="决定"
      min-width="320"
    >
      <template #default="{ row }">
        {{ decisionText(row) }}
      </template>
    </el-table-column>
    <el-table-column
      label="政策数"
      width="90"
      align="right"
    >
      <template #default="{ row }">
        <el-button
          link
          type="primary"
          :aria-label="`看提出「${row.name}」的 ${row.policy_count} 条政策`"
          @click="emit('rows', row)"
        >
          {{ row.policy_count?.toLocaleString() }}
        </el-button>
      </template>
    </el-table-column>
    <el-table-column
      v-if="pending && canDecide"
      label="决定"
      width="256"
      class-name="candidates-table__decide table-action"
    >
      <template #default="{ row }">
        <DecisionButtons
          v-if="row.id"
          :candidate="row"
          :can-write-codebook="canWriteCodebook"
          :busy="busy && busy.id === row.id ? busy.mode : null"
          @open="mode => emit('open', row, mode)"
        />
      </template>
    </el-table-column>
    <el-table-column
      v-else-if="status === '已驳回' && canDecide"
      label="操作"
      width="120"
      class-name="table-action"
    >
      <template #default="{ row }">
        <button
          type="button"
          class="row-action row-action--primary"
          :disabled="Boolean(reopeningId)"
          :aria-busy="reopeningId === row.id"
          @click="emit('reopen', row)"
        >
          {{ reopeningId === row.id ? '改判中…' : '改判回待审' }}
        </button>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
/* 全局 .data-table 的单元格内边距更具体，这里要写到 td 才压得住 */
.candidates-table :deep(td.el-table__cell.el-table__expanded-cell) {
  padding: 0 var(--zt-space-4) var(--zt-space-4) 76px;
  background: var(--zt-surface-subtle);
}

.candidates-table :deep(tr.is-open > td.el-table__cell) {
  border-bottom-color: transparent;
  background: var(--zt-surface-subtle);
}

/* 按钮宽度刚好；别让单元格的省略号规则在后面多画一个「…」 */
.candidates-table :deep(td.candidates-table__decide .cell) {
  overflow: visible;
  text-overflow: clip;
}

.candidates-table__name {
  padding: 0;
  border: 0;
  background: none;
  color: var(--zt-ink-900);
  font: inherit;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.candidates-table__name:hover {
  color: var(--el-color-primary);
}

.candidates-table__level {
  padding: 1px 8px;
  border: 1px solid var(--zt-warning-border);
  border-radius: 4px;
  background: var(--zt-warning-soft);
  color: var(--zt-warning-text);
  font-size: 12px;
  white-space: nowrap;
}

.candidates-table__level--link {
  border-color: var(--zt-teal-line);
  background: var(--zt-teal-soft);
  color: var(--zt-teal-text);
}
</style>
