<script setup lang="ts" generic="T extends { id: string }">
import { computed, ref, shallowRef, onMounted, onBeforeUnmount, type ShallowRef } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { useNarrowViewport } from '@/composables/useNarrowViewport'
import { layoutDataColumns } from './dataColumnLayout'
import type { DataColumn } from './dataColumns'
import { fieldLink, fieldText, fieldValue } from './cellValue'
import { buildDetailSections } from './detailSections'
import DetailSections from './DetailSections.vue'
import type { EditorGroup } from './editorGroups'
import ListEmpty from './ListEmpty.vue'
import type { GroupRow } from './rowGroups'
import RowActions from './RowActions.vue'
import { useGroupedRows, type SelectableTable } from './useGroupedRows'
const props = defineProps<{
  items: T[]; columns: readonly DataColumn[]; selected: string[]; titleKey: string; summaryKeys?: string[];
  canWrite: boolean; loading: boolean; filtered: boolean; detailTitle?: string;
  /** 编辑表单的分组：详情按它分类展示，表单里没有的列归到「系统信息」。 */
  groups?: readonly EditorGroup[];
  /** 有独立详情页的模块：标题、「查看」「编辑」都跳过去，不再开抽屉；「编辑」打开就是编辑状态。index 是行在当前页的位置。 */
  detailRoute?: (row: T, index: number) => RouteLocationRaw;
  /** 首列加勾选框，用于批量操作；只勾当前页。 */
  selectable?: boolean;
  /**
   * 一条记录拆成好几行时（如一条政策解读出十几行行业场景）：挨着的同一标题分成一组，组前一行分组标题条
   * 写标题和 groupMeta 给的说明，表格里不再有标题列。勾选、查看、编辑仍是每行一套，标题条上的勾选框勾整组；
   * 只分挨着的，翻页后下一页开头再起一组。
   */
  groupByTitle?: boolean;
  /** 分组标题条上标题下面的一句说明，如「11 条解读 · 待验证 9」。 */
  groupMeta?: (rows: T[]) => string;
}>()
const emit = defineEmits<{ edit: [row: T]; reset: []; 'selection-change': [rows: T[]] }>()
const SELECTION_WIDTH = 44
const table = ref<SelectableTable<T | GroupRow<T>>>()
defineExpose({ clearSelection: () => table.value?.clearSelection() })
const detail: ShallowRef<T | null> = shallowRef(null)
const detailOpen = ref(false)
const narrow = useNarrowViewport()
// 分组时标题写在分组标题条上，表格里不再出标题列。
const displayed = computed(() => props.columns.filter(col => props.selected.includes(col.prop)
  && !(props.groupByTitle && col.prop === props.titleKey)))
const summaryColumns = computed(() => (props.summaryKeys ?? props.selected)
  .map(key => displayed.value.find(col => col.prop === key))
  .filter((col): col is DataColumn => !!col && col.prop !== props.titleKey)
  .slice(0, 3))
const root = ref<HTMLElement>()
const availableWidth = ref(0)
const actionWidth = computed(() => props.canWrite ? 140 : 84)
const fixedWidth = computed(() => actionWidth.value + (props.selectable ? SELECTION_WIDTH : 0))
const laidOut = computed(() => layoutDataColumns(displayed.value, availableWidth.value - 2, fixedWidth.value))
const totalWidth = computed(() => laidOut.value.reduce((sum, col) => sum + col.width, fixedWidth.value) + 2)
let resizeObserver: ResizeObserver | undefined
onMounted(() => {
  if (!root.value) return
  availableWidth.value = root.value.clientWidth
  resizeObserver = new ResizeObserver(([entry]) => {
    if (!entry) return
    availableWidth.value = entry.contentRect.width
  })
  resizeObserver.observe(root.value)
})
onBeforeUnmount(() => resizeObserver?.disconnect())
const value = fieldValue
const text = fieldText
const link = fieldLink
/** 叠在一格里的下级字段（二级 › 三级），空的跳过 */
function stackText(row: T, col: DataColumn): string {
  return (col.stack ?? []).map(key => value(row, key)).filter(Boolean).join(' › ')
}
const { rows, at, isGroup, spanMethod, rowClass, onSelect, onSelectionChange } = useGroupedRows<T>({
  items: () => props.items,
  titleOf: row => value(row, props.titleKey),
  enabled: () => !!props.groupByTitle,
  selectable: () => !!props.selectable,
  otherColumns: computed(() => laidOut.value.length + (availableWidth.value > totalWidth.value ? 1 : 0) + 1),
  table,
  emitSelection: selection => emit('selection-change', selection),
})
const firstColumn = computed(() => laidOut.value[0]?.prop)
const sections = computed(() => buildDetailSections(props.columns, props.groups))
function open(row: T) { detail.value = row; detailOpen.value = true }
function editDetail() { if (detail.value) { emit('edit', detail.value); detailOpen.value = false } }
function closeDetail() { detailOpen.value = false }
// 详情页按地址栏的 edit=1 直接进编辑状态。
function editRoute(row: T, index: number): RouteLocationRaw {
  const to = props.detailRoute!(row, index)
  return typeof to === 'string' ? { path: to, query: { edit: '1' } } : { ...to, query: { ...to.query, edit: '1' } }
}
</script>
<template>
  <div
    ref="root"
    class="business-table"
    :style="{ '--business-table-view': `${availableWidth}px` }"
  >
    <el-table
      v-if="!narrow"
      ref="table"
      v-loading="loading"
      :data="rows"
      :fit="false"
      style="width: 100%"
      row-key="id"
      :span-method="groupByTitle ? spanMethod : undefined"
      :row-class-name="groupByTitle ? rowClass : undefined"
      class="data-table business-table__desktop"
      :class="{ 'business-table--grouped': groupByTitle }"
      @select="onSelect"
      @selection-change="onSelectionChange"
    >
      <template #empty>
        <ListEmpty
          :loading="loading"
          :filtered="filtered"
          @reset="emit('reset')"
        />
      </template>
      <el-table-column
        v-if="selectable"
        type="selection"
        :width="SELECTION_WIDTH"
        class-name="table-selection"
      />
      <el-table-column
        v-for="col in laidOut"
        :key="col.prop"
        :prop="col.prop"
        :label="col.label"
        :width="col.width"
        :show-overflow-tooltip="col.prop !== titleKey && !col.stack"
        :label-class-name="col.ai ? 'column-ai' : undefined"
      >
        <template #header>
          <span
            class="column-heading"
            :title="col.ai ? `${col.fullLabel || col.label}：AI 打标写入，人工验证后 AI 不再覆盖` : col.fullLabel || col.label"
          ><span
            v-if="col.ai"
            class="ai-mark"
            aria-label="AI 打标"
          >AI</span>{{ col.label }}</span>
        </template>
        <template #default="{ row }">
          <div
            v-if="isGroup(row)"
            class="group-bar"
          >
            <template v-if="col.prop === firstColumn">
              <RouterLink
                v-if="detailRoute && row.group.rows[0]"
                class="group-bar__title"
                :to="detailRoute(row.group.rows[0], at(row.group.rows[0]))"
                :title="row.group.title"
              >
                {{ row.group.title || '未命名记录' }}
              </RouterLink>
              <span
                v-else
                class="group-bar__title"
              >{{ row.group.title || '未命名记录' }}</span>
              <span
                v-if="groupMeta"
                class="group-bar__meta"
              >{{ groupMeta(row.group.rows) }}</span>
            </template>
          </div>
          <template v-else-if="col.prop === titleKey">
            <!-- Element Plus 注册列时会拿空行（没有 id）试渲染一次插槽，不判断就会按空 id 生成地址、控制台报错 -->
            <RouterLink
              v-if="detailRoute && row.id"
              class="record-title"
              :to="detailRoute(row, at(row))"
              :title="text(row, col)"
            >
              {{ text(row, col) }}
            </RouterLink>
            <button
              v-else
              type="button"
              class="record-title"
              :title="text(row, col)"
              @click="open(row)"
            >
              {{ text(row, col) }}
            </button>
          </template>
          <span
            v-else-if="col.stack"
            class="cell-stack"
            :title="[text(row, col), stackText(row, col)].filter(Boolean).join(' › ')"
          >
            <span class="cell-stack__main">{{ text(row, col) }}</span>
            <span
              v-if="stackText(row, col)"
              class="cell-stack__sub"
            >{{ stackText(row, col) }}</span>
          </span>
          <a
            v-else-if="col.link && link(row, col)"
            :href="link(row, col)"
            target="_blank"
            rel="noopener noreferrer"
          >{{ text(row, col) }}</a>
          <span
            v-else
            class="cell-text"
            :title="text(row, col)"
            :class="{ 'cell-text--wrap': col.wrap, 'record-boolean': ['need_interpret', 'is_penetrate', 'has_subsidy'].includes(col.prop) }"
          >{{ text(row, col) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        v-if="availableWidth > totalWidth"
        :width="availableWidth - totalWidth"
        class-name="table-remainder"
      />
      <el-table-column
        label="操作"
        :width="actionWidth"
        class-name="table-action"
      >
        <template #default="{ row }">
          <RowActions
            v-if="!isGroup(row) && row.id"
            :view="detailRoute ? detailRoute(row, at(row)) : undefined"
            :edit="detailRoute ? editRoute(row, at(row)) : undefined"
            :can-edit="canWrite"
            @view="open(row)"
            @edit="emit('edit', row)"
          />
        </template>
      </el-table-column>
    </el-table>
    <div
      v-if="narrow"
      v-loading="loading"
      class="business-table__mobile"
    >
      <ListEmpty
        v-if="!items.length"
        :loading="loading"
        :filtered="filtered"
        @reset="emit('reset')"
      />
      <article
        v-for="(row, index) in items"
        :key="row.id"
        class="mobile-record"
      >
        <RouterLink
          v-if="detailRoute"
          class="record-title"
          :to="detailRoute(row, index)"
        >
          {{ value(row, titleKey) || '未命名记录' }}
        </RouterLink>
        <button
          v-else
          type="button"
          class="record-title"
          @click="open(row)"
        >
          {{ value(row, titleKey) || '未命名记录' }}
        </button>
        <dl>
          <template
            v-for="col in summaryColumns"
            :key="col.prop"
          >
            <dt :title="col.fullLabel || col.label">
              {{ col.label }}
            </dt><dd>{{ text(row, col) }}</dd>
          </template>
        </dl>
        <div class="mobile-record__actions">
          <RouterLink
            v-if="detailRoute"
            class="table-link"
            :to="detailRoute(row, index)"
          >
            查看详情
          </RouterLink>
          <RouterLink
            v-if="detailRoute && canWrite && row.id"
            class="table-link"
            :to="editRoute(row, index)"
          >
            编辑
          </RouterLink>
          <el-button
            v-if="!detailRoute"
            text
            type="primary"
            @click="open(row)"
          >
            查看详情
          </el-button><el-button
            v-if="canWrite && !detailRoute"
            text
            type="primary"
            @click="emit('edit', row)"
          >
            编辑
          </el-button>
        </div>
      </article>
    </div>
    <el-drawer
      v-model="detailOpen"
      :title="detailTitle || '记录详情'"
      size="min(880px, 100vw)"
      class="record-detail"
      destroy-on-close
    >
      <template v-if="detail">
        <h2>{{ value(detail, titleKey) || '未命名记录' }}</h2>
        <DetailSections
          :row="detail"
          :sections="sections"
        />
        <!-- 模块可在详情里补自己的内容（如趋势图），不必另造一个平行抽屉。 -->
        <slot
          name="detail-extra"
          :row="detail"
        />
      </template>
      <template #footer>
        <el-button @click="detailOpen = false">
          关闭
        </el-button>
        <!-- 看完就能做的动作（如标为人工验证）放在这里，不用回列表勾选。 -->
        <slot
          v-if="detail"
          name="detail-actions"
          :row="detail"
          :close="closeDetail"
        /><el-button
          v-if="canWrite"
          type="primary"
          @click="editDetail"
        >
          编辑记录
        </el-button>
      </template>
    </el-drawer>
  </div>
</template>
<style scoped>
.business-table { min-width: 0; }
.business-table__desktop { border: 0; }
.column-heading { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 20px; }
.business-table__desktop :deep(th.el-table__cell) { height: 40px; padding: 5px 0; }
.business-table__desktop :deep(td.el-table__cell) { height: 44px; padding: 6px 0; }
.business-table__desktop :deep(.el-button.is-link) { min-height: 24px; height: 24px; }
.business-table__desktop :deep(.cell) { padding: 0 12px; line-height: 22px; }
.cell-text--wrap { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.business-table__desktop :deep(.table-action) { position: sticky; right: 0; z-index: 2; background: var(--zt-panel); box-shadow: -8px 0 10px -8px var(--zt-shadow-edge); }
.business-table__desktop :deep(th.table-action) { background: var(--el-table-header-bg-color); }

.record-title { padding: 0; border: 0; font: inherit; font-weight: 500; line-height: 22px; background: none; color: var(--zt-ink-900); text-align: left; cursor: pointer; display: block; max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.record-title:hover { color: var(--zt-blue-600); text-decoration: underline; }
a.record-title { text-decoration: none; }
/* AI 打标写入的列：表头淡紫底，列名前一个小「AI」标记 */
.business-table__desktop :deep(th.column-ai + th:not(.column-ai)) { box-shadow: inset 1px 0 0 var(--zt-ai-line); }
.ai-mark { display: inline-block; margin-right: 6px; padding: 0 4px; border: 1px solid var(--zt-ai-line); border-radius: 3px; color: var(--zt-ai-text); background: var(--zt-panel); font-size: 11px; font-weight: 600; line-height: 16px; vertical-align: 1px; }

/* 分组标题条：一条政策一条，横跨整行；横向滚动时标题停在左边 */
.business-table__desktop :deep(tr.group-row > td.el-table__cell) { height: auto; padding: 10px 0 8px; background: var(--zt-surface-subtle); border-top: 1px solid var(--zt-border); }
.business-table__desktop :deep(tr.group-row > td.el-table__cell .cell) { overflow: visible; }
.business-table__desktop :deep(tr.group-row:hover > td.el-table__cell) { background: var(--zt-surface-subtle); }
.business-table__desktop :deep(tr.group-row + tr > td.el-table__cell) { border-top: 0; }
.group-bar { position: sticky; left: 12px; display: flex; flex-direction: column; gap: 2px; max-width: min(960px, calc(var(--business-table-view, 100vw) - 96px)); }
.group-bar__title { overflow: hidden; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; line-height: 22px; text-decoration: none; white-space: nowrap; text-overflow: ellipsis; }
a.group-bar__title:hover { color: var(--zt-blue-600); text-decoration: underline; }
.group-bar__meta { color: var(--zt-ink-500); font-size: 12px; line-height: 18px; }
.cell-stack { display: flex; flex-direction: column; min-width: 0; }
.cell-stack__main, .cell-stack__sub { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.cell-stack__main { color: var(--zt-ink-900); }
.cell-stack__sub { color: var(--zt-ink-500); font-size: 12px; line-height: 18px; }
.table-link { color: var(--zt-blue-600); font-size: 14px; text-decoration: none; }
.table-link + .table-link { margin-left: 12px; }
.table-link:hover { text-decoration: underline; }
.record-boolean { padding: 2px 9px; background: var(--zt-soft); border: 1px solid var(--zt-border); border-radius: 4px; }
a { color: var(--zt-blue-600); }

.record-detail h2 { margin: 0 0 20px; line-height: 1.6; font-size: 20px; overflow-wrap: anywhere; }
@media (max-width: 767px) {
 .business-table__desktop { display: none; }
 .business-table__mobile { display: block; }
 .mobile-record { padding: 16px; border-bottom: 1px solid var(--zt-border); }
 .mobile-record:last-child { border-bottom: 0; }
 .mobile-record .record-title { display: block; font-size: 15px; white-space: normal; font-weight: 600; }
 .mobile-record dl { display: grid; grid-template-columns: 85px minmax(0, 1fr); gap: 7px 12px; font-size: 13px; margin: 14px 0 4px; }
 .mobile-record dt { color: var(--zt-ink-500); }
 .mobile-record dd { margin: 0; overflow-wrap: anywhere; }
 .mobile-record__actions { display: flex; justify-content: flex-end; }
}
</style>
