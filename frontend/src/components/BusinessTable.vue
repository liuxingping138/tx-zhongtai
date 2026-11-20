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
import RowActions from './RowActions.vue'
import TableSkeleton from './TableSkeleton.vue'
const props = defineProps<{
  items: T[]; columns: readonly DataColumn[]; selected: string[]; titleKey: string; summaryKeys?: string[];
  canWrite: boolean; loading: boolean; filtered: boolean; detailTitle?: string;
  /** 编辑表单的分组：详情按它分类展示，表单里没有的列归到「系统信息」。 */
  groups?: readonly EditorGroup[];
  /** 有独立详情页的模块：标题、「查看」「编辑」都跳过去，不再开抽屉；「编辑」打开就是编辑状态。index 是行在当前页的位置。 */
  detailRoute?: (row: T, index: number) => RouteLocationRaw;
  /** 首列加勾选框，用于批量操作；只勾当前页。 */
  selectable?: boolean;
  /** 自定义操作列宽度（当使用 #row-actions 插槽时可调宽）。 */
  actionWidth?: number;
}>()
const emit = defineEmits<{ edit: [row: T]; reset: []; 'selection-change': [rows: T[]] }>()
const SELECTION_WIDTH = 44
const table = ref<{ clearSelection: () => void }>()
defineExpose({ clearSelection: () => table.value?.clearSelection() })
const detail: ShallowRef<T | null> = shallowRef(null)
const detailOpen = ref(false)
const narrow = useNarrowViewport()
const displayed = computed(() => props.columns.filter(col => props.selected.includes(col.prop)))
const summaryColumns = computed(() => (props.summaryKeys ?? props.selected)
  .map(key => displayed.value.find(col => col.prop === key))
  .filter((col): col is DataColumn => !!col && col.prop !== props.titleKey)
  .slice(0, 3))
const root = ref<HTMLElement>()
const availableWidth = ref(0)
const resolvedActionWidth = computed(() => props.actionWidth ?? (props.canWrite ? 140 : 84))
const fixedWidth = computed(() => resolvedActionWidth.value + (props.selectable ? SELECTION_WIDTH : 0))
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
  >
    <TableSkeleton
      v-if="loading && items.length === 0"
      :columns="displayed.length || 6"
      :has-selection="selectable"
      :has-actions="true"
    />
    <template v-else>
      <el-table
        v-if="!narrow"
        ref="table"
        :data="items"
        :fit="false"
        style="width: 100%"
        row-key="id"
        class="data-table business-table__desktop"
        :class="{ 'is-refreshing': loading }"
        @selection-change="(rows: T[]) => emit('selection-change', rows)"
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
          :show-overflow-tooltip="col.prop !== titleKey && !col.stack && !col.tags && !$slots[`cell-${col.prop}`]"
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
          <template #default="{ row, $index }">
            <template v-if="col.prop === titleKey">
              <!-- Element Plus 注册列时会拿空行（没有 id）试渲染一次插槽，不判断就会按空 id 生成地址、控制台报错 -->
              <RouterLink
                v-if="detailRoute && row.id"
                class="record-title"
                :to="detailRoute(row, $index)"
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
            <!-- 模块自己画这一格（如行内启停开关）：插槽名 cell-列名 -->
            <slot
              v-else-if="$slots[`cell-${col.prop}`]"
              :name="`cell-${col.prop}`"
              :row="row"
            />
            <el-tag
              v-else-if="col.tags && value(row, col.prop)"
              size="small"
              :type="col.tags[value(row, col.prop)] ?? 'info'"
              disable-transitions
            >
              {{ text(row, col) }}
            </el-tag>
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
          :width="resolvedActionWidth"
          class-name="table-action"
        >
          <template #default="{ row, $index }">
            <template v-if="row?.id">
              <slot
                name="row-actions"
                :row="row"
                :index="$index"
              >
                <RowActions
                  :view="detailRoute ? detailRoute(row, $index) : undefined"
                  :edit="detailRoute ? editRoute(row, $index) : undefined"
                  :can-edit="canWrite"
                  @view="open(row)"
                  @edit="emit('edit', row)"
                />
              </slot>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <div
        v-if="narrow"
        class="business-table__mobile"
        :class="{ 'is-refreshing': loading }"
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
    </template>
    <el-drawer
      v-model="detailOpen"
      :title="detailTitle || '记录详情'"
      size="min(720px, 100vw)"
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
:global(html[data-density="compact"]) .business-table__desktop :deep(th.el-table__cell),
:global(html[data-density="compact"]) .business-table__desktop :deep(td.el-table__cell) { height: 32px; }
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

.cell-stack { display: flex; flex-direction: column; min-width: 0; }
.cell-stack__main, .cell-stack__sub { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.cell-stack__main { color: var(--zt-ink-900); }
.cell-stack__sub { color: var(--zt-ink-500); font-size: 12px; line-height: 18px; }
.table-link { color: var(--zt-blue-600); font-size: 14px; text-decoration: none; }
.table-link + .table-link { margin-left: 12px; }
.table-link:hover { text-decoration: underline; }
.record-boolean { padding: 2px 9px; background: var(--zt-soft); border: 1px solid var(--zt-border); border-radius: 4px; }
a { color: var(--zt-blue-600); }

.record-detail h2 { margin: 0 0 20px; line-height: 1.4; font-size: 18px; font-weight: 650; color: var(--zt-ink-900); letter-spacing: -0.01em; overflow-wrap: anywhere; }
.is-refreshing {
  opacity: 0.65;
  pointer-events: none;
  transition: opacity 0.2s ease;
}
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
