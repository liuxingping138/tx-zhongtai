<script setup lang="ts">
import { computed } from 'vue'

import type { RunRows, RunRowStatus } from '@/api/ai'
import { itemSummary, rowLayout } from './runRowLayout'

/**
 * 任务的逐行结果：这一行用到的输入、解析出的字段，失败的写原因，格式不对的附上模型原话。
 * 样本试跑和批量任务详情共用。只列前 50 行，完整结果看下载的 Excel。
 */
const props = defineProps<{ rows: RunRows | null; loading?: boolean; empty?: string }>()
const failedOnly = defineModel<boolean>('failedOnly', { default: false })

const STATUS: Record<RunRowStatus, string> = { done: '成功', failed: '失败', format: '格式不对', pending: '未跑' }
const summary = computed(() => {
  const rows = props.rows
  if (!rows) return ''
  const scope = failedOnly.value ? `失败 ${rows.matched} 行` : `共 ${rows.total} 行`
  return rows.matched > rows.items.length ? `${scope}，这里列前 ${rows.items.length} 行` : scope
})
// 一条政策展开成好几个场景时，一样的字段列一次、每个场景折叠成一行，不然第一行就要滚好几屏。
const layouts = computed(() => new Map((props.rows?.items ?? []).map(row => [row.row, rowLayout(row.items, props.rows?.fields ?? [])])))
</script>

<template>
  <section
    v-loading="loading && !rows"
    class="run-rows"
    aria-label="逐行结果"
  >
    <div
      v-if="rows"
      class="run-rows__bar"
    >
      <span>{{ summary }}</span>
      <el-switch
        v-model="failedOnly"
        size="small"
        active-text="只看失败"
      />
    </div>
    <p
      v-if="rows && !rows.items.length"
      class="run-rows__empty"
    >
      {{ failedOnly ? '没有失败的行' : (empty || '还没有结果') }}
    </p>
    <ol
      v-if="rows && rows.items.length"
      class="run-rows__list"
    >
      <li
        v-for="row in rows.items"
        :key="row.row"
        class="run-row"
        :class="`is-${row.status}`"
      >
        <div class="run-row__head">
          <span class="run-row__no">第 {{ row.row }} 行</span>
          <span class="run-row__status">{{ row.items.length > 1 ? `${STATUS[row.status]} · 解析出 ${row.items.length} 条` : STATUS[row.status] }}</span>
        </div>
        <dl
          v-if="rows.columns.length"
          class="run-row__inputs"
        >
          <template
            v-for="column in rows.columns"
            :key="column"
          >
            <dt>{{ column }}</dt>
            <dd>{{ row.inputs[column] || '—' }}</dd>
          </template>
        </dl>
        <template v-if="row.items.length > 1">
          <dl
            v-if="layouts.get(row.row)?.shared.length"
            class="run-row__fields"
          >
            <template
              v-for="field in layouts.get(row.row)?.shared"
              :key="field"
            >
              <dt>{{ field }}</dt>
              <dd>{{ row.items[0]?.[field] || '—' }}</dd>
            </template>
          </dl>
          <details
            v-for="(item, index) in row.items"
            :key="index"
            class="run-row__item"
          >
            <summary>{{ index + 1 }}. {{ itemSummary(item, layouts.get(row.row)?.own ?? []) }}</summary>
            <dl class="run-row__fields">
              <template
                v-for="field in layouts.get(row.row)?.own"
                :key="field"
              >
                <dt>{{ field }}</dt>
                <dd>{{ item[field] || '—' }}</dd>
              </template>
            </dl>
          </details>
        </template>
        <dl
          v-for="(item, index) in row.items.length > 1 ? [] : row.items"
          :key="index"
          class="run-row__fields"
        >
          <template
            v-for="field in rows.fields"
            :key="field"
          >
            <dt>{{ field }}</dt>
            <dd>{{ item[field] || '—' }}</dd>
          </template>
        </dl>
        <p
          v-if="row.error"
          class="run-row__error"
        >
          {{ row.error }}
        </p>
        <p
          v-if="row.answer"
          class="run-row__answer"
        >
          {{ row.answer }}
        </p>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.run-rows { display: flex; flex-direction: column; min-height: 80px; }
.run-rows__bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 0 10px; color: var(--zt-ink-500); font-size: 12px; }
.run-rows__empty { margin: 16px 0; color: var(--zt-ink-500); font-size: 13px; text-align: center; }
.run-rows__list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.run-row { padding: 10px 12px; border: 1px solid var(--zt-border); border-left-width: 3px; border-radius: 6px; background: var(--zt-panel); font-size: 13px; }
.run-row.is-done { border-left-color: var(--zt-success); }
.run-row.is-failed { border-left-color: var(--el-color-danger); }
.run-row.is-format { border-left-color: var(--zt-warning); }
.run-row.is-pending { border-left-color: var(--zt-muted-mark); }
.run-row__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.run-row__no { color: var(--zt-ink-900); font-weight: 600; font-variant-numeric: tabular-nums; }
.run-row__status { color: var(--zt-ink-500); font-size: 12px; }
.is-failed .run-row__status { color: var(--el-color-danger); }
.is-format .run-row__status { color: var(--zt-warning-text); }
.run-row dl { display: grid; grid-template-columns: minmax(64px, max-content) minmax(0, 1fr); gap: 2px 12px; margin: 0; }
.run-row dt { color: var(--zt-ink-500); white-space: nowrap; }
.run-row dd { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.run-row__inputs { padding-bottom: 6px; color: var(--zt-ink-500); font-size: 12px; }
.run-row__inputs dd { display: -webkit-box; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.run-row__fields { padding-top: 6px; border-top: 1px dashed var(--zt-border); color: var(--zt-ink-900); }
.run-row__item { border-top: 1px dashed var(--zt-border); }
.run-row__item summary { padding: 6px 0; color: var(--zt-ink-900); cursor: pointer; overflow-wrap: anywhere; }
.run-row__item summary:hover { color: var(--zt-blue-600); }
.run-row__item .run-row__fields { padding: 0 0 8px 16px; border-top: 0; }
.run-row__error { margin: 6px 0 0; color: var(--el-color-danger); font-size: 12px; overflow-wrap: anywhere; }
.run-row__answer { margin: 6px 0 0; padding: 6px 8px; border-radius: 4px; background: var(--zt-soft); color: var(--zt-ink-700); font-size: 12px; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
