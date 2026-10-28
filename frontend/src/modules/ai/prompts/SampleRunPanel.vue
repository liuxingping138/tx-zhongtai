<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { getSampleRun, startSampleRun, stopSampleRun, type AiModel, type BatchRun, type PromptTemplate, type SampleRunState } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { RUN_STATUS_TEXT, formatYuan, isActive, runStatusType } from '../shared/aiText'
import RunRows from '../shared/RunRows.vue'
import { downloadSampleFile } from '../shared/downloads'

/**
 * 样本试跑：用保存的草稿把测试样本的前几条整批跑一遍，逐行看结果。
 * 试发只看第一行；整批跑过、结果没问题，再请管理员上线。跑完可以下载结果 Excel 给别人看。
 */
const props = defineProps<{
  template: PromptTemplate | null
  model: AiModel | undefined
  thinking: boolean
  canRun: boolean
  canExport: boolean
  dirty: boolean
}>()
const emit = defineEmits<{ changed: [run: BatchRun]; upload: [] }>()

const MAX_ROWS = 50
const POLL_MS = 2000
const state = ref<SampleRunState>({ run: null, rows: null })
const loading = ref(false)
const busy = ref(false)
const failedOnly = ref(false)
const limit = ref(10)
let timer = 0
let sequence = 0

const run = computed(() => state.value.run)
const running = computed(() => Boolean(run.value && isActive(run.value.status)))
const maxRows = computed(() => Math.min(MAX_ROWS, props.template?.excel_rows ?? 0))
const stale = computed(() => {
  const current = run.value
  const template = props.template
  if (!current || !template) return false
  return current.prompt_content !== template.content || current.output_fields !== template.output_fields
})
// 试跑用模板上选定的模型：和上线后跑的是同一个，没选就先选，不拿别的顶替。
const blocker = computed(() => {
  const template = props.template
  if (!template?.excel_name) return '先上传测试样本 Excel（政策类也可以在左边「测试样本」里从数据库取）'
  if (props.dirty) return '有未保存的修改，保存后再试跑'
  if (!template.content.trim()) return '提示词还是空的，写好保存后再试跑'
  if (!template.model_id) return '先在左边「模型」里选好模型并保存'
  if (!props.model?.available) return `「${template.model_name}」现在不可用，换一个模型再试跑`
  return ''
})

const visibleRows = computed(() => {
  const rows = state.value.rows
  if (!rows || !failedOnly.value) return rows
  const items = rows.items.filter(item => item.status === 'failed' || item.status === 'format')
  return { ...rows, items, matched: items.length }
})

async function load(quiet = false): Promise<void> {
  const template = props.template
  window.clearTimeout(timer)
  if (!template) { state.value = { run: null, rows: null }; return }
  const current = ++sequence
  loading.value = !quiet
  try {
    const next = await getSampleRun(template.id)
    if (current !== sequence) return
    state.value = next
    if (next.run) emit('changed', next.run)
  } catch (error) {
    if (!quiet) ElMessage.error(errorMessage(error, '试跑结果加载失败，请重试'))
  } finally {
    if (current === sequence) loading.value = false
  }
  if (current === sequence && running.value) timer = window.setTimeout(() => void load(true), POLL_MS)
}

watch(() => props.template?.id, () => {
  failedOnly.value = false
  limit.value = Math.min(10, maxRows.value || 10)
  void load()
}, { immediate: true })
// 刚传上样本时给默认 10 条；换了更短的样本时不超过它的行数。
watch(maxRows, (value, previous) => {
  if (value && !previous) limit.value = Math.min(10, value)
  else if (value && limit.value > value) limit.value = value
})
onBeforeUnmount(() => { sequence++; window.clearTimeout(timer) })

async function start(): Promise<void> {
  const template = props.template
  if (!template || blocker.value || busy.value) return
  busy.value = true
  try {
    state.value = await startSampleRun(template.id, { thinking: props.thinking, limit: limit.value })
    if (state.value.run) emit('changed', state.value.run)
    failedOnly.value = false
    await load(true)
  } catch (error) {
    ElMessage.error(errorMessage(error, '试跑没能开始，请重试'))
  } finally {
    busy.value = false
  }
}

async function download(): Promise<void> {
  const current = run.value
  const template = props.template
  if (!current || !template) return
  try {
    await downloadSampleFile(template.id, current.id, 'result', `${template.title}-样本试跑结果.xlsx`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败，请重试'))
  }
}

async function stop(): Promise<void> {
  const template = props.template
  if (!template) return
  busy.value = true
  try {
    state.value = await stopSampleRun(template.id)
    await load(true)
  } catch (error) {
    ElMessage.error(errorMessage(error, '停止失败，请重试'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="sample">
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
        <el-input-number
          id="sample-limit"
          v-model="limit"
          size="small"
          :min="1"
          :max="maxRows || 1"
          :disabled="running || !maxRows"
          controls-position="right"
        />
        <span>条</span>
        <el-button
          v-if="running"
          size="small"
          :loading="busy"
          :disabled="run?.status === 'stopping'"
          @click="stop"
        >
          停止
        </el-button>
        <el-button
          v-else
          size="small"
          type="primary"
          :loading="busy"
          :disabled="Boolean(blocker)"
          @click="start"
        >
          开始试跑
        </el-button>
      </div>
    </div>
    <p
      v-if="canRun"
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

    <div
      v-if="run"
      class="sample__summary"
    >
      <div class="sample__status">
        <el-tag
          :type="runStatusType(run.status)"
          size="small"
        >
          {{ RUN_STATUS_TEXT[run.status] }}
        </el-tag>
        <span>{{ run.done_count }}/{{ run.total_count }} 条</span>
        <span
          v-if="run.failed_count"
          class="sample__failed"
        >失败 {{ run.failed_count }}{{ run.format_failed_count ? `（格式不对 ${run.format_failed_count}）` : '' }}</span>
        <span class="sample__cost">{{ formatYuan(run.inference_cost + run.search_cost) }}</span>
        <el-button
          v-if="canExport && run.files.result"
          link
          type="primary"
          size="small"
          @click="download"
        >
          下载结果
        </el-button>
      </div>
      <el-progress
        v-if="running"
        :percentage="run.percent"
        :show-text="false"
        :stroke-width="4"
      />
      <p class="sample__meta">
        {{ run.created_by_name }} · {{ run.created_at }}
      </p>
      <p
        v-if="stale && !running"
        class="sample__stale"
      >
        草稿在这次试跑之后改过，结果可能过时，建议重新试跑
      </p>
    </div>

    <RunRows
      v-if="run"
      v-model:failed-only="failedOnly"
      class="sample__rows"
      :rows="visibleRows"
      :loading="loading"
      empty="排队中，马上开始"
    />
    <p
      v-else-if="!loading"
      class="sample__empty"
    >
      试发只问第一行。上线前用测试样本整批跑一遍，逐行看解析出的字段和失败原因。
    </p>
  </div>
</template>

<style scoped>
.sample { display: flex; flex-direction: column; gap: 10px; flex: 1; min-height: 0; overflow-y: auto; padding: 12px 16px 16px; }
.sample__launch { display: flex; align-items: center; justify-content: space-between; gap: 8px 12px; flex-wrap: wrap; }
.sample__source { display: flex; align-items: baseline; gap: 8px; min-width: 0; margin: 0; color: var(--zt-ink-700); font-size: 13px; }
.sample__source strong { overflow: hidden; color: var(--zt-ink-900); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.sample__source span { flex: none; color: var(--zt-ink-500); font-size: 12px; }
.sample__controls { display: flex; align-items: center; gap: 6px; color: var(--zt-ink-700); font-size: 13px; }
.sample__controls .el-input-number { width: 84px; }
.sample__controls .el-button { margin-left: 4px; }
.sample__hint, .sample__meta { margin: 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
.sample__hint.is-blocked { color: var(--zt-warning-text); }
.sample__summary { display: grid; gap: 6px; padding: 10px 12px; border-radius: 6px; background: var(--zt-soft); }
.sample__status { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; font-size: 13px; font-variant-numeric: tabular-nums; }
.sample__failed { color: var(--el-color-danger); }
.sample__cost { margin-left: auto; color: var(--zt-ink-500); }
.sample__stale { margin: 0; color: var(--zt-warning-text); font-size: 12px; }
.sample__empty { margin: 24px 8px; color: var(--zt-ink-500); font-size: 13px; line-height: 1.8; text-align: center; }
</style>
