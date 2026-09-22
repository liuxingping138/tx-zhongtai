<script setup lang="ts" generic="T extends { id: string }">
import { computed, ref, shallowRef, onMounted, onBeforeUnmount, type ShallowRef } from 'vue'
import { useNarrowViewport } from '@/composables/useNarrowViewport'
import { layoutDataColumns } from './dataColumnLayout'
import type { DataColumn } from './dataColumns'
import ListEmpty from './ListEmpty.vue'
import { formatTime } from '@/utils/time'
const props = defineProps<{
  items: T[]; columns: readonly DataColumn[]; selected: string[]; titleKey: string; summaryKeys?: string[];
  canWrite: boolean; loading: boolean; filtered: boolean; detailTitle?: string;
}>()
const emit = defineEmits<{ edit: [row: T]; reset: [] }>()
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
const actionWidth = computed(() => props.canWrite ? 116 : 72)
const laidOut = computed(() => layoutDataColumns(displayed.value, availableWidth.value - 2, actionWidth.value))
const totalWidth = computed(() => laidOut.value.reduce((sum, col) => sum + col.width, actionWidth.value) + 2)
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
function value(row: T, key: string) { return String((row as Record<string, unknown>)[key] ?? '') }
function text(row: T, col: DataColumn) { const val = value(row, col.prop); return val ? col.time ? formatTime(val) : val : '—' }
function link(row: T, col: DataColumn) {
  const val = value(row, col.prop).trim()
  if (!val) return undefined
  try { const url = new URL(/^https?:\/\//i.test(val) ? val : `https://${val}`); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined } catch { return undefined }
}
function open(row: T) { detail.value = row; detailOpen.value = true }
function editDetail() { if (detail.value) { emit('edit', detail.value); detailOpen.value = false } }
</script>
<template>
  <div
    ref="root"
    class="business-table"
  >
    <el-table
      v-if="!narrow"
      v-loading="loading"
      :data="items"
      :fit="false"
      style="width: 100%"
      row-key="id"
      class="data-table business-table__desktop"
    >
      <template #empty>
        <ListEmpty
          :loading="loading"
          :filtered="filtered"
          @reset="emit('reset')"
        />
      </template>
      <el-table-column
        v-for="col in laidOut"
        :key="col.prop"
        :prop="col.prop"
        :label="col.label"
        :width="col.width"
        :show-overflow-tooltip="col.prop !== titleKey"
      >
        <template #header>
          <span
            class="column-heading"
            :title="col.fullLabel || col.label"
          >{{ col.label }}</span>
        </template>
        <template #default="{ row }">
          <template v-if="col.prop === titleKey">
            <button
              type="button"
              class="record-title"
              :title="text(row, col)"
              @click="open(row)"
            >
              {{ text(row, col) }}
            </button>
          </template>
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
          <el-button
            link
            type="primary"
            @click="open(row)"
          >
            查看
          </el-button>
          <el-button
            v-if="canWrite"
            link
            type="primary"
            @click="emit('edit', row)"
          >
            编辑
          </el-button>
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
        v-for="row in items"
        :key="row.id"
        class="mobile-record"
      >
        <button
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
          <el-button
            text
            type="primary"
            @click="open(row)"
          >
            查看详情
          </el-button><el-button
            v-if="canWrite"
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
      size="min(720px, 100vw)"
      class="record-detail"
      destroy-on-close
    >
      <template v-if="detail">
        <h2>{{ value(detail, titleKey) || '未命名记录' }}</h2>
        <dl>
          <template
            v-for="col in columns"
            :key="col.prop"
          >
            <dt>{{ col.fullLabel || col.label }}</dt><dd>
              <a
                v-if="col.link && link(detail, col)"
                :href="link(detail, col)"
                target="_blank"
                rel="noopener noreferrer"
              >{{ text(detail, col) }}</a>
              <template v-else>
                {{ text(detail, col) }}
              </template>
            </dd>
          </template>
        </dl>
        <!-- 模块可在详情里补自己的内容（如趋势图），不必另造一个平行抽屉。 -->
        <slot
          name="detail-extra"
          :row="detail"
        />
      </template>
      <template #footer>
        <el-button @click="detailOpen = false">
          关闭
        </el-button><el-button
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
.business-table__desktop :deep(.table-action) { position: sticky; right: 0; z-index: 2; background: #fff; box-shadow: -8px 0 10px -8px rgba(32, 50, 76, 0.18); }
.business-table__desktop :deep(th.table-action) { background: #f0f4f9; }

.record-title { padding: 0; border: 0; font: inherit; font-weight: 500; line-height: 22px; background: none; color: var(--zt-ink-900); text-align: left; cursor: pointer; display: block; max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.record-title:hover { color: var(--zt-blue-600); text-decoration: underline; }
.record-boolean { padding: 2px 9px; background: var(--zt-soft); border: 1px solid var(--zt-border); border-radius: 4px; }
a { color: var(--zt-blue-600); }

.record-detail h2 { margin: 0 0 24px; line-height: 1.6; font-size: 20px; overflow-wrap: anywhere; }
.record-detail dl { display: grid; grid-template-columns: 145px minmax(0, 1fr); margin: 0; }
.record-detail dt, .record-detail dd { margin: 0; padding: 12px 0; border-bottom: 1px solid var(--zt-border); font-size: 14px; line-height: 1.7; overflow-wrap: anywhere; white-space: pre-wrap; }
.record-detail dt { padding-right: 16px; color: var(--zt-ink-500); }
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
 .record-detail dl { grid-template-columns: 110px minmax(0, 1fr); }
}
</style>
