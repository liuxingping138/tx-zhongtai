<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { missingFieldsWarning } from '../shared/outputFields'

import type { AiModel, PromptTemplate, RunRow } from '@/api/ai'
import { RUN_STATUS_TEXT, formatYuan, runStatusType } from '../shared/aiText'
import SampleResultsDrawer from './SampleResultsDrawer.vue'
import SamplePreviewTable from './SamplePreviewTable.vue'
import SampleStrip from './SampleStrip.vue'
import { compareText, isProblem, rowNote, rowsToWatch, shortTime } from './sampleView'
import { sampleCurrent } from './templateStatus'
import type { SampleRun } from './useSampleRun'

/**
 * 样本试跑：用保存的草稿把测试样本的前几条整批跑一遍。
 * 右栏先给结论：一格一行看好坏，一句话说和上一次比修好了几行、弄坏了几行，再列出要看的那几行；逐行细看在抽屉里。
 */
const props = defineProps<{
  sample: SampleRun
  template: PromptTemplate | null
  model: AiModel | undefined
  thinking: boolean
  canRun: boolean
  canExport: boolean
  dirty: boolean
  activeRow?: number
}>()
const emit = defineEmits<{ upload: []; trial: [row: number]; edit: [] }>()

const MAX_ROWS = 50
const limit = ref(10)
const drawer = ref(false)
const focusRow = ref(0)

const run = computed(() => props.sample.run.value)
const rows = computed(() => props.sample.state.value.rows)
const compare = computed(() => props.sample.state.value.compare)
const running = computed(() => props.sample.running.value)
const workerOffline = computed(() => props.sample.workerOffline.value)
const maxRows = computed(() => Math.min(MAX_ROWS, props.template?.excel_rows ?? 0))
const limitLocked = computed(() => running.value || !maxRows.value)
const watched = computed(() => rowsToWatch(rows.value?.items ?? []))
const notes = computed(() => new Map(watched.value.map(row => [row.row, rowNote(row, rows.value?.fields ?? [])])))
const compared = computed(() => compare.value?.fixed !== undefined)
// 草稿在这次试跑之后又改过（提示词、字段、模型、码表、测试样本都算）：结果可能过时，重跑失败的行也还是用
// 旧提示词，所以只给「再跑一次」。和模板列表、新建批量任务的提醒同一个口径。
const stale = computed(() => {
  const current = run.value
  const template = props.template
  return Boolean(current && template && !sampleCurrent(current, template))
})
const retryable = computed(() => Boolean(props.canRun && run.value?.can_retry && !stale.value))
// 试跑用模板上选定的模型：和上线后跑的是同一个，没选就先选，不拿别的顶替。
const noFields = computed(() => (props.template ? missingFieldsWarning(props.template.content, props.template.fields) : ''))
const blocker = computed(() => {
  const template = props.template
  if (!template?.excel_name) return '先上传测试样本 Excel（政策类也可以在左边「测试样本」里从数据库取）'
  if (props.dirty) return '有未保存的修改，保存后再试跑'
  if (!template.content.trim()) return '提示词还是空的，写好保存后再试跑'
  if (!template.model_id) return '先在左边「模型」里选好模型并保存'
  if (!props.model?.available) return `「${template.model_name}」现在不可用，换一个模型再试跑`
  return ''
})
const allGood = computed(() => {
  const items = rows.value?.items ?? []
  if (!run.value || running.value || !items.length || watched.value.length) return ''
  return compared.value ? `${items.length} 行都成功，和上一次结果一样。` : `${items.length} 行都成功。`
})

watch(() => props.template?.id, () => { limit.value = Math.min(10, maxRows.value || 10) })
// 刚传上样本时给默认 10 条；换了更短的样本时不超过它的行数。
watch(maxRows, (value, previous) => {
  if (value && !previous) limit.value = Math.min(10, value)
  else if (value && limit.value > value) limit.value = value
})

function title(row: RunRow): string {
  const column = rows.value?.columns[0]
  return (column && row.inputs[column]) || `第 ${row.row} 行`
}

function open(row = 0): void {
  focusRow.value = row
  drawer.value = true
}

async function start(): Promise<void> {
  if (blocker.value) return
  await props.sample.start(limit.value, props.thinking)
}
</script>

<template>
  <div class="sample">
    <div class="sample__scroll">
      <div class="sample__launch">
        <p class="sample__source">
          <template v-if="template?.excel_name">
            <strong>{{ template.excel_name }}</strong><span>共 {{ template.excel_rows }} 行</span>
          </template>
          <template v-else>
            还没有测试样本
          </template>
        </p>
        <div
          v-if="canRun"
          class="sample__controls"
        >
          <label for="sample-limit">跑前</label>
          <!-- Element Plus 只在挂载时写 aria-valuemax / aria-disabled：上限、能不能改变了就重新挂载，读屏和自动化测试才不会读到旧状态。 -->
          <el-input-number
            id="sample-limit"
            :key="`${maxRows}:${limitLocked}`"
            v-model="limit"
            size="small"
            :min="1"
            :max="maxRows || 1"
            :disabled="limitLocked"
            controls-position="right"
          />
          <span>条</span>
          <el-button
            v-if="running"
            size="small"
            :loading="sample.busy.value"
            :disabled="run?.status === 'stopping'"
            @click="sample.stop"
          >
            停止
          </el-button>
          <el-button
            v-else
            size="small"
            :type="run ? undefined : 'primary'"
            :loading="sample.busy.value"
            :disabled="Boolean(blocker)"
            @click="start"
          >
            {{ run ? '再跑一次' : '开始试跑' }}
          </el-button>
        </div>
      </div>
      <!-- 没设输出字段：试跑照样能跑，但解析不出任何列、也不检查格式，「全部成功」是假的；只提醒、不拦 -->
      <p
        v-if="canRun && noFields"
        class="sample__hint is-blocked"
        role="status"
      >
        {{ noFields }}
      </p>
      <p
        v-if="canRun && (blocker || !run)"
        class="sample__hint"
        :class="{ 'is-blocked': blocker }"
      >
        {{ blocker || `用保存的草稿和「${model?.name}」逐条提问，按条计费，最多 ${MAX_ROWS} 条` }}
        <el-button
          v-if="!template?.excel_name"
          link
          type="primary"
          size="small"
          @click="emit('upload')"
        >
          上传测试样本
        </el-button>
      </p>
      <section
        v-if="run"
        class="sample__result"
        :class="{ 'is-refreshing': sample.loading.value }"
        aria-labelledby="sample-run-title"
      >
        <div class="sample__head">
          <h3 id="sample-run-title">
            第 {{ run.no }} 次试跑
          </h3>
          <el-tag
            :type="runStatusType(run.status)"
            size="small"
          >
            {{ RUN_STATUS_TEXT[run.status] }}
          </el-tag>
          <span class="sample__meta">{{ shortTime(run.created_at) }} {{ run.created_by_name }}</span>
          <span class="sample__cost">{{ formatYuan(run.inference_cost + run.search_cost) }}</span>
        </div>
        <el-progress
          v-if="running"
          :percentage="run.percent"
          :show-text="false"
          :stroke-width="4"
        />
        <SampleStrip
          v-if="rows?.items.length"
          :rows="rows.items"
          :compared="compared"
          :active-row="activeRow"
          @pick="open"
        />
        <p
          v-if="compare"
          class="sample__versus"
        >
          {{ compareText(compare) }}
        </p>
        <p
          v-if="workerOffline"
          class="sample__stale"
        >
          AI 执行进程不在线，这次试跑暂时不会开始，请联系管理员检查 ai-worker
        </p>
        <p
          v-if="stale && !running"
          class="sample__stale"
        >
          草稿在这次试跑之后改过，结果可能过时，点「再跑一次」看改过的效果
        </p>
      </section>
      <SamplePreviewTable
        v-if="rows?.items.length && !running"
        :columns="rows.columns"
        :fields="rows.fields"
        :items="rows.items"
        :can-run="canRun"
        :active-row="activeRow"
        @pick="open"
        @trial="row => emit('trial', row)"
      />
      <template v-if="watched.length">
        <div class="sample__sect">
          <h4>要看的 {{ watched.length }} 行</h4>
          <span>有问题的在前，点行号看整行</span>
        </div>
        <ul class="sample__items">
          <li
            v-for="row in watched"
            :key="row.row"
            class="sample__item"
          >
            <button
              type="button"
              class="sample__no"
              :class="`is-${row.status}`"
              :aria-label="`看第 ${row.row} 行`"
              @click="open(row.row)"
            >
              {{ row.row }}
            </button>
            <div class="sample__text">
              <p class="sample__title">
                {{ title(row) }}
              </p>
              <p class="sample__note">
                <span
                  v-for="item in notes.get(row.row)?.labels"
                  :key="item.text"
                  class="sample__label"
                  :class="`is-${item.tone}`"
                >{{ item.text }}</span>{{ notes.get(row.row)?.text }}
              </p>
            </div>
            <el-button
              v-if="canRun && isProblem(row)"
              size="small"
              @click="emit('trial', row.row)"
            >
              试发这一行
            </el-button>
          </li>
        </ul>
      </template>
      <p
        v-else-if="allGood"
        class="sample__good"
      >
        {{ allGood }}
      </p>
      <p
        v-if="!run && !sample.loading.value"
        class="sample__empty"
      >
        试发一次问一行。上线前用测试样本整批跑一遍，逐行看解析出的字段和失败原因，还能和上一次试跑比。
      </p>
    </div>
    <footer
      v-if="run"
      class="sample__foot"
    >
      <el-button
        type="primary"
        @click="open()"
      >
        逐行看结果
      </el-button>
      <el-button
        v-if="canExport && run.files.result"
        @click="sample.download"
      >
        下载结果
      </el-button>
      <span class="sample__spacer" />
      <el-button
        v-if="retryable"
        title="用这次的提示词重问失败和没跑到的行"
        :loading="sample.busy.value"
        @click="sample.retry"
      >
        重跑失败的 {{ run.pending_count }} 条
      </el-button>
    </footer>
    <SampleResultsDrawer
      v-model="drawer"
      :sample="sample"
      :template="template"
      :focus-row="focusRow"
      :can-run="canRun"
      :can-export="canExport"
      :retryable="retryable"
      @trial="row => emit('trial', row)"
      @edit="emit('edit')"
    />
  </div>
</template>

<style scoped>
.sample { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.sample__scroll { display: flex; flex-direction: column; gap: 10px; flex: 1; min-height: 0; overflow-y: auto; padding: 12px 16px 16px; }
.sample__scroll > * { flex: none; }
.sample__launch { display: flex; align-items: center; justify-content: space-between; gap: 8px 12px; flex-wrap: wrap; }
.sample__source { display: flex; align-items: baseline; gap: 8px; min-width: 0; margin: 0; color: var(--zt-ink-700); font-size: 13px; }
.sample__source strong { overflow: hidden; color: var(--zt-ink-900); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.sample__source span { flex: none; color: var(--zt-ink-500); font-size: 12px; }
.sample__controls { display: flex; align-items: center; gap: 6px; color: var(--zt-ink-700); font-size: 13px; }
.sample__controls .el-input-number { width: 84px; }
.sample__controls .el-button { margin-left: 4px; }
.sample__hint, .sample__empty { margin: 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
.sample__hint.is-blocked { color: var(--zt-warning-text); }
.sample__result { display: grid; gap: 12px; padding: 14px 14px 12px; border: 1px solid var(--zt-border); border-radius: 8px; }
.sample__head { display: flex; align-items: center; gap: 8px; min-width: 0; font-variant-numeric: tabular-nums; }
.sample__head h3 { margin: 0; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
.sample__meta { overflow: hidden; color: var(--zt-ink-500); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.sample__cost { margin-left: auto; color: var(--zt-ink-900); font-size: 13px; font-weight: 600; }
.sample__versus { margin: 0; padding-top: 10px; border-top: 1px dashed var(--zt-border); color: var(--zt-ink-700); font-size: 12px; line-height: 1.7; }
.sample__stale { margin: 0; color: var(--zt-warning-text); font-size: 12px; }
.sample__sect { display: flex; align-items: baseline; gap: 8px; margin-top: 8px; }
.sample__sect h4 { margin: 0; color: var(--zt-ink-900); font-size: 13px; }
.sample__sect span { color: var(--zt-ink-500); font-size: 12px; }
.sample__items { margin: 0; padding: 0; list-style: none; }
.sample__item { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; align-items: start; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--zt-divider); }
.sample__item:last-child { border-bottom: 0; }
.sample__no { display: grid; place-items: center; width: 28px; height: 28px; padding: 0; border: 1px solid var(--zt-success-border); border-radius: 4px; background: var(--zt-success-soft); color: var(--zt-success-text); font: 600 12px/1 var(--zt-font); cursor: pointer; }
.sample__no.is-failed { border-color: var(--zt-danger-text); background: var(--zt-danger-text); color: var(--el-color-white); }
.sample__no.is-format { border-color: var(--zt-warning); background: repeating-linear-gradient(135deg, var(--zt-warning-soft) 0 5px, var(--zt-warning-border) 5px 10px); color: var(--zt-warning-text); }
.sample__no:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.sample__text { min-width: 0; }
.sample__title { margin: 0; overflow: hidden; color: var(--zt-ink-900); font-size: 13px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.sample__note { margin: 3px 0 0; color: var(--zt-ink-700); font-size: 12px; line-height: 1.7; word-break: break-all; }
.sample__label { display: inline-block; margin-right: 6px; padding: 0 5px; border-radius: 3px; font-weight: 600; line-height: 18px; }
.sample__label.is-failed { background: var(--zt-danger-soft); color: var(--zt-danger-text); }
.sample__label.is-format { background: var(--zt-warning-soft); color: var(--zt-warning-text); }
.sample__label.is-changed { background: var(--el-color-primary-light-9); color: var(--zt-blue-700); }
.sample__label.is-fixed { background: var(--zt-success-soft); color: var(--zt-success-text); }
.sample__good { margin: 0; color: var(--zt-success-text); font-size: 13px; }
.sample__foot { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--zt-border); background: var(--zt-surface-subtle); }
.sample__foot .el-button { margin: 0; }
.sample__spacer { flex: 1; }
</style>
