<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Download } from '@element-plus/icons-vue'

import type { PromptTemplate } from '@/api/ai'
import { formatYuan } from '../shared/aiText'
import SampleRowDetail from './SampleRowDetail.vue'
import { ROW_STATUS_TEXT, fieldCell, isProblem, previousText, rowCounts, rowMatches, shortTime } from './sampleView'
import type { SampleRun } from './useSampleRun'

/**
 * 逐行看样本试跑：每个输出字段一列，和上次不同的格子写出上次的值；点一行展开，输入、这次的回答、上次的回答并排对照。
 * 看哪一次、和哪一次比都能换。
 */
const props = defineProps<{
  sample: SampleRun
  template: PromptTemplate | null
  focusRow: number
  canRun: boolean
  canExport: boolean
  retryable: boolean
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ trial: [row: number]; edit: [] }>()

type Filter = 'all' | 'problem' | 'changed'
const filter = ref<Filter>('all')
const keyword = ref('')
const expanded = ref(new Set<number>())

const state = computed(() => props.sample.state.value)
const run = computed(() => state.value.run)
const rows = computed(() => state.value.rows)
const fields = computed(() => rows.value?.fields ?? [])
const items = computed(() => rows.value?.items ?? [])
const counts = computed(() => rowCounts(items.value))
const problems = computed(() => items.value.filter(isProblem).length)
const compared = computed(() => state.value.compare?.fixed !== undefined)
const compareValue = computed(() => state.value.compare?.run.id ?? 'none')
const others = computed(() => state.value.history.filter(item => item.id !== run.value?.id))
const visible = computed(() => items.value.filter(row => {
  if (filter.value === 'problem' && !isProblem(row)) return false
  if (filter.value === 'changed' && !row.change) return false
  return rowMatches(row, keyword.value)
}))
const span = computed(() => 2 + (rows.value?.columns.length ?? 0) + Math.max(fields.value.length, 1))
const brokeCount = computed(() => items.value.filter(row => row.change === 'broke').length)
const footText = computed(() => {
  if (!problems.value) return compared.value ? '没有问题行。' : '每一行都解析成功了。'
  const broke = brokeCount.value ? `其中 ${brokeCount.value} 行上次是成功的，多半和这次改的提示词有关。` : ''
  return `${problems.value} 行有问题。${broke}`
})

watch(open, value => {
  if (!value) return
  filter.value = 'all'
  keyword.value = ''
  expanded.value = new Set(props.focusRow ? [props.focusRow] : [])
  if (props.focusRow) void nextTick(() => document.getElementById(`sample-row-${props.focusRow}`)?.scrollIntoView({ block: 'center' }))
})

function toggle(row: number): void {
  const next = new Set(expanded.value)
  if (!next.delete(row)) next.add(row)
  expanded.value = next
}

const pickRun = (id: string) => void props.sample.view(id, '')
const pickCompare = (id: string) => void props.sample.view(run.value?.id ?? '', id)
const backToEdit = () => { open.value = false; emit('edit') }
const trial = (row: number) => { open.value = false; emit('trial', row) }
</script>

<template>
  <el-drawer
    v-model="open"
    size="min(1120px, 92vw)"
    class="editor-overlay sample-results"
  >
    <template #header="{ titleId }">
      <div class="results__head">
        <h2 :id="titleId">
          样本试跑结果
        </h2>
        <label class="results__pick">看
          <el-select
            :model-value="run?.id ?? ''"
            size="small"
            aria-label="看哪一次试跑"
            @update:model-value="pickRun"
          >
            <el-option
              v-for="item in state.history"
              :key="item.id"
              :value="item.id"
              :label="`第 ${item.no} 次（${shortTime(item.created_at)}）`"
            />
          </el-select>
        </label>
        <label class="results__pick">对比
          <el-select
            :model-value="compareValue"
            size="small"
            aria-label="和哪一次比"
            @update:model-value="pickCompare"
          >
            <el-option
              v-for="item in others"
              :key="item.id"
              :value="item.id"
              :label="`第 ${item.no} 次（${shortTime(item.created_at)}）`"
            />
            <el-option
              value="none"
              label="不对比"
            />
          </el-select>
        </label>
        <span
          v-if="run"
          class="results__meta"
        >{{ run.input_name }} 前 {{ run.total_count }} 行，费用 {{ formatYuan(run.inference_cost + run.search_cost) }}</span>
        <el-button
          v-if="canExport && run?.files.result"
          :icon="Download"
          @click="sample.download"
        >
          下载结果
        </el-button>
      </div>
    </template>
    <div class="results">
      <div class="results__tools">
        <el-radio-group
          v-model="filter"
          size="small"
          class="ai-seg"
          aria-label="按结果看"
        >
          <el-radio-button value="all">
            全部 {{ items.length }}
          </el-radio-button>
          <el-radio-button value="problem">
            有问题 {{ problems }}
          </el-radio-button>
          <el-radio-button
            v-if="compared"
            value="changed"
          >
            和上次不同 {{ counts.changed }}
          </el-radio-button>
        </el-radio-group>
        <el-input
          v-model="keyword"
          size="small"
          clearable
          class="results__find"
          placeholder="在结果里找"
          aria-label="在结果里找"
        />
        <span class="results__hint">点一行展开，看输入、这次和上次的回答</span>
      </div>
      <div
        v-loading="sample.loading.value"
        class="results__wrap"
      >
        <table v-if="rows">
          <thead>
            <tr class="results__group">
              <th
                scope="colgroup"
                class="is-no"
              />
              <th
                v-if="rows.columns.length"
                scope="colgroup"
                :colspan="rows.columns.length"
              >
                输入
              </th>
              <th
                scope="colgroup"
                :colspan="Math.max(fields.length, 1)"
                class="is-output"
              >
                {{ fields.length ? '输出字段' : '模型回答' }}
              </th>
              <th
                scope="colgroup"
                class="is-status"
              />
            </tr>
            <tr class="results__cols">
              <th
                scope="col"
                class="is-no"
              >
                行
              </th>
              <th
                v-for="column in rows.columns"
                :key="column"
                scope="col"
              >
                {{ column }}
              </th>
              <th
                v-for="field in fields"
                :key="field"
                scope="col"
              >
                {{ field }}
              </th>
              <th
                v-if="!fields.length"
                scope="col"
              >
                回答
              </th>
              <th
                scope="col"
                class="is-status"
              >
                结果
              </th>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="row in visible"
              :key="row.row"
            >
              <tr
                :id="`sample-row-${row.row}`"
                class="results__row"
                :class="[`is-${row.status}`, { 'is-changed': row.change, 'is-open': expanded.has(row.row) }]"
                @click="toggle(row.row)"
              >
                <td class="results__no">
                  <button
                    type="button"
                    :aria-expanded="expanded.has(row.row)"
                    :aria-label="`展开第 ${row.row} 行`"
                    @click.stop="toggle(row.row)"
                  >
                    {{ row.row }}
                  </button>
                </td>
                <td
                  v-for="column in rows.columns"
                  :key="column"
                  class="results__input"
                  :title="row.inputs[column]"
                >
                  {{ row.inputs[column] || '—' }}
                </td>
                <td
                  v-for="field in fields"
                  :key="field"
                  class="results__field"
                  :title="fieldCell(row, field).now"
                >
                  <span :class="{ 'is-empty': !fieldCell(row, field).now }">{{ fieldCell(row, field).now || '—' }}</span>
                  <span
                    v-if="fieldCell(row, field).before !== null"
                    class="results__was"
                    :title="`上次：${fieldCell(row, field).before || '空'}`"
                  >上次 <s>{{ fieldCell(row, field).before || '空' }}</s></span>
                </td>
                <td
                  v-if="!fields.length"
                  class="results__field"
                  :title="row.answer"
                >
                  {{ row.answer || '—' }}
                </td>
                <td class="results__status">
                  <span :class="`is-${row.status}`">{{ ROW_STATUS_TEXT[row.status] }}</span>
                  <span
                    v-if="row.items.length > 1"
                    class="results__note"
                  >解析出 {{ row.items.length }} 条</span>
                  <span
                    v-if="row.change === 'fixed' || row.change === 'broke' || (isProblem(row) && row.previous)"
                    class="results__note"
                  >{{ previousText(row) }}</span>
                  <span
                    v-else-if="row.change === 'changed'"
                    class="results__note"
                  >字段变了</span>
                  <span
                    v-if="isProblem(row) && row.error"
                    class="results__error"
                  >{{ row.error }}</span>
                </td>
              </tr>
              <tr
                v-if="expanded.has(row.row)"
                class="results__detail"
              >
                <td :colspan="span">
                  <SampleRowDetail
                    :row="row"
                    :columns="rows.columns"
                    :fields="fields"
                    :run-no="run?.no ?? 0"
                    :compare-no="state.compare?.run.no ?? 0"
                    :can-run="canRun"
                    @trial="trial(row.row)"
                  />
                </td>
              </tr>
            </template>
            <tr v-if="!visible.length">
              <td
                :colspan="span"
                class="results__empty"
              >
                {{ keyword ? '没有符合条件的行' : filter === 'problem' ? '没有有问题的行' : filter === 'changed' ? '和上次比没有变化的行' : '还没有结果' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="results__foot">
        <p>{{ footText }}</p>
        <el-button @click="backToEdit">
          回去改提示词
        </el-button>
        <el-button
          v-if="retryable && run"
          type="primary"
          :loading="sample.busy.value"
          @click="sample.retry"
        >
          重跑失败的 {{ run.pending_count }} 条
        </el-button>
      </footer>
    </div>
  </el-drawer>
</template>

<style scoped>
/* 抽屉挂在 body 下：表格铺满抽屉，不要通用编辑抽屉的内边距和灰底。 */
:global(.sample-results.el-drawer .el-drawer__header) { padding: 14px 20px 14px 24px; }
:global(.sample-results.el-drawer .el-drawer__body) { padding: 0; background: var(--zt-panel); }
.results { display: flex; flex-direction: column; height: 100%; }
.results__head { display: flex; flex: 1; align-items: center; gap: 14px; min-width: 0; }
.results__head h2 { margin: 0; color: var(--zt-ink-900); font-size: 18px; }
.results__pick { display: flex; align-items: center; gap: 6px; color: var(--zt-ink-500); font-size: 13px; }
.results__pick .el-select { width: 170px; }
.results__meta { flex: 1; min-width: 0; overflow: hidden; color: var(--zt-ink-500); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.results__head .el-button { margin: 0; }
.results__tools { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 16px; padding: 12px 24px; border-bottom: 1px solid var(--zt-divider); }
.results__find { width: 200px; }
.results__hint { margin-left: auto; color: var(--zt-ink-500); font-size: 12px; }
.results__wrap { flex: 1; min-height: 0; overflow: auto; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th { position: sticky; z-index: 1; background: var(--zt-table-head); text-align: left; white-space: nowrap; }
.results__group th { top: 0; height: 28px; padding: 0 14px; color: var(--zt-ink-500); font-size: 12px; font-weight: 500; border-bottom: 1px solid var(--zt-border); }
.results__group th.is-output { border-inline: 1px solid var(--zt-border); color: var(--zt-blue-700); }
.results__cols th { top: 28px; height: 38px; padding: 0 14px; color: var(--zt-ink-900); font-size: 13px; font-weight: 600; border-bottom: 1px solid var(--zt-border); }
th.is-no { left: 0; z-index: 3; }
th.is-status { right: 0; z-index: 3; border-left: 1px solid var(--zt-border); }
td { padding: 10px 14px; border-bottom: 1px solid var(--zt-divider); background: var(--zt-panel); color: var(--zt-ink-700); font-size: 13px; line-height: 1.6; vertical-align: top; }
.results__row { cursor: pointer; }
.results__row:hover td { background: var(--zt-row-hover); }
.results__row.is-failed td { background: var(--zt-danger-soft); }
.results__row.is-format td, .results__row.is-open td, .results__detail td { background: var(--zt-warning-soft); }
.results__row.is-open td { border-bottom-color: transparent; }
.results__row.is-changed .results__no { box-shadow: inset 3px 0 0 var(--zt-blue-600); }
.results__no { position: sticky; left: 0; z-index: 2; width: 52px; }
.results__no button { padding: 0; border: 0; background: none; color: var(--zt-ink-400); font: 600 13px/1.6 var(--zt-font); cursor: pointer; }
.results__row.is-changed .results__no button { color: var(--zt-blue-700); }
.results__no button:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.results__input { max-width: 260px; overflow: hidden; color: var(--zt-ink-900); text-overflow: ellipsis; white-space: nowrap; }
.results__field { min-width: 112px; max-width: 300px; color: var(--zt-ink-900); }
.results__field > span:first-child { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.results__field .is-empty { color: var(--zt-ink-400); }
.results__was { display: block; overflow: hidden; color: var(--zt-ink-400); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.results__status { position: sticky; right: 0; z-index: 2; width: 148px; border-left: 1px solid var(--zt-divider); white-space: nowrap; }
.results__status .is-done { color: var(--zt-success-text); font-weight: 600; }
.results__status .is-failed { color: var(--zt-danger-text); font-weight: 600; }
.results__status .is-format { color: var(--zt-warning-text); font-weight: 600; }
.results__status .is-pending { color: var(--zt-ink-400); }
.results__note { display: block; color: var(--zt-blue-700); font-size: 12px; }
.results__error { display: block; max-width: 220px; overflow: hidden; color: var(--zt-ink-500); font-size: 12px; text-overflow: ellipsis; }
.results__detail td { padding: 0 14px 16px 52px; }
.results__empty { padding: 32px; color: var(--zt-ink-500); text-align: center; }
.results__foot { display: flex; align-items: center; gap: 10px; padding: 12px 24px; border-top: 1px solid var(--zt-divider); background: var(--zt-surface-subtle); }
.results__foot p { flex: 1; margin: 0; color: var(--zt-ink-700); font-size: 13px; }
.results__foot .el-button { margin: 0; }
</style>
