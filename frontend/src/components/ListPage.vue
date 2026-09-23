<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { Warning } from '@element-plus/icons-vue'
import ScrollPort from './ScrollPort.vue'
withDefaults(defineProps<{
  title: string; hint?: string; error?: string; total: number; page: number;
  pageSize: number; loading?: boolean; hidePager?: boolean;
}>(), { hint: '', error: '', loading: false, hidePager: false })
const emit = defineEmits<{
  'update:page': [value: number]; 'update:pageSize': [value: number]; change: []; retry: [];
}>()
const surface = ref<HTMLElement>()
async function onPage(value: number) {
  emit('update:page', value)
  await nextTick()
  emit('change')
  surface.value?.scrollIntoView({ block: 'start' })
}
async function onSize(value: number) {
  emit('update:pageSize', value)
  emit('update:page', 1)
  await nextTick()
  emit('change')
}
</script>
<template>
  <div class="list-page">
    <header class="list-page__heading">
      <h1>{{ title }}</h1>
      <p v-if="hint">
        {{ hint }}
      </p>
    </header>
    <section
      v-if="$slots.summary"
      class="summary-band"
      aria-label="概览"
    >
      <slot name="summary" />
    </section>
    <section
      v-if="$slots.filters"
      class="filter-card"
      aria-label="筛选条件"
    >
      <slot name="filters" />
    </section>
    <section
      ref="surface"
      class="table-card"
      :aria-label="title + '列表'"
      :aria-busy="loading"
    >
      <div class="list-page__toolbar">
        <span
          class="list-page__total"
          role="status"
          aria-live="polite"
        >
          <template v-if="error">数据加载失败</template>
          <template v-else-if="loading">正在加载…</template>
          <template v-else>共 <strong>{{ total.toLocaleString('zh-CN') }}</strong> 条记录</template>
        </span>
        <div class="list-page__actions">
          <slot name="actions" /><slot name="tools" />
        </div>
      </div>
      <div
        v-if="error"
        class="list-error"
        role="alert"
      >
        <el-icon :size="28">
          <Warning />
        </el-icon>
        <h2>暂时无法加载数据</h2><p>{{ error }}</p>
        <el-button
          type="primary"
          :loading="loading"
          @click="$emit('retry')"
        >
          重新加载
        </el-button>
      </div>
      <ScrollPort
        v-else
        class="list-page__results"
      >
        <slot />
      </ScrollPort>
      <div
        v-if="!hidePager && !error"
        class="pagination-row"
      >
        <span class="pagination-range">第 {{ total ? (page - 1) * pageSize + 1 : 0 }}–{{ Math.min(page * pageSize, total) }} 条</span>
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          :pager-count="5"
          :disabled="loading"
          layout="sizes, prev, pager, next"
          @update:current-page="onPage"
          @update:page-size="onSize"
        />
      </div>
    </section>
  </div>
</template>
<style scoped>
.list-page { display: flex; flex-direction: column; gap: 0; min-width: 0; min-height: calc(100dvh - 108px); max-height: calc(100dvh - 108px); }
.list-page__heading { padding: 0 0 14px; }
.list-page__heading h1 { margin: 0; font-size: var(--zt-title-size); line-height: 1.4; font-weight: 650; color: var(--zt-ink-900); }
.list-page__heading p { margin: 4px 0 0; font-size: 13px; line-height: 1.6; color: var(--zt-ink-500); }
/* 概览不挤压结果区。监测页自然纵向滚动，表格随窗口高度变化；收起概览可直接专注列表。 */
.summary-band { flex: 0 0 auto; margin-bottom: 8px; }
.list-page:has(.summary-band) { max-height: none; }
.list-page:has(.summary-band) .table-card { flex: none; }
.list-page:has(.summary-band) .scroll-port.list-page__results {
  height: clamp(440px, calc(100dvh - 220px), 880px);
  min-height: 440px;
  flex: none;
}
.filter-card { padding: 14px 16px 16px; margin-bottom: 4px; background: #f6f8fb; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); }
.table-card { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; scroll-margin-top: 12px; }
.list-page__toolbar { min-height: 56px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 0; }
.list-page__total { flex-shrink: 0; color: var(--zt-ink-700); font-size: 14px; font-variant-numeric: tabular-nums; }
.list-page__total strong { color: var(--zt-ink-900); font-weight: 650; }
.list-page__actions { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 8px; }
.list-page__actions :deep(.el-button + .el-button) { margin-left: 0; }
.list-page__actions :deep(.el-upload) { display: inline-flex; }
.list-page__results { flex: 1 1 0; min-width: 0; min-height: 0; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); overflow: hidden; }
.list-page__results :deep(.el-table),
.list-page__results :deep(.el-table__inner-wrapper),
.list-page__results :deep(.el-table__header-wrapper),
.list-page__results :deep(.el-table__body-wrapper),
.list-page__results :deep(.el-table__body),
.list-page__results :deep(.el-scrollbar),
.list-page__results :deep(.el-scrollbar__wrap),
.list-page__results :deep(.el-scrollbar__view) { overflow: visible !important; height: auto !important; max-height: none !important; }
.list-page__results :deep(.el-scrollbar__bar) { display: none !important; }
.list-page__results :deep(.el-table__header-wrapper) { position: sticky; top: 0; z-index: 4; }
.list-error { min-height: max(360px, calc(100dvh - 400px)); display: flex; align-items: center; justify-content: center; flex-direction: column; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); color: var(--zt-ink-700); text-align: center; padding: 24px; }
.list-error h2 { font-size: 17px; margin: 16px 0 0; }
.list-error p { max-width: 560px; overflow-wrap: anywhere; font-size: 14px; line-height: 1.7; }
@media (max-width: 1000px) { .list-page { min-height: calc(100dvh - 100px); max-height: calc(100dvh - 100px); } }
@media (max-width: 767px) {
 .list-page { min-height: calc(100dvh - 92px); max-height: none; }
 .list-page__results { overflow: visible; min-height: 0; }
 .list-page__heading { padding-bottom: 16px; }
 .list-page__heading p { margin-top: 5px; }
 .filter-card { padding: 12px; }
 .list-page__toolbar { align-items: flex-start; flex-direction: column; padding: 14px 0; }
 .list-page__actions { justify-content: flex-start; gap: 8px; width: 100%; }
 .list-page__actions :deep(.el-button) { padding: 0 10px; }
}
</style>
