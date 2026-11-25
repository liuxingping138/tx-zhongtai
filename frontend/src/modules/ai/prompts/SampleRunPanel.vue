<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { missingFieldsWarning } from '../shared/outputFields'

import type { AiModel, PromptTemplate, RunRow } from '@/api/ai'
import { RUN_STATUS_TEXT, formatYuan, runStatusType } from '../shared/aiText'
import SamplePreviewTable from './SamplePreviewTable.vue'
import SampleResultsDrawer from './SampleResultsDrawer.vue'
import SampleStrip from './SampleStrip.vue'
import { compareText, isProblem, rowNote, rowsToWatch, shortTime } from './sampleView'
import { sampleCurrent } from './templateStatus'
import type { SampleRun } from './useSampleRun'

/**
 * 样本试跑：窄栏分屏模式下使用「需关注行 / 全部结果」紧凑诊断列表（避免 420px 内硬塞 8 列截断宽表），
 * 多列宽表统一交给 1120px 对比抽屉或「全屏看结果」模式承载。
 */
const props = withDefaults(defineProps<{
  sample: SampleRun
  template: PromptTemplate | null
  model: AiModel | undefined
  thinking: boolean
  wide?: boolean
  canRun: boolean
  canExport: boolean
  dirty: boolean
  activeRow?: number
}>(), { wide: false, activeRow: 1 })
const emit = defineEmits<{ upload: []; trial: [row: number]; edit: [] }>()

const MAX_ROWS = 50
const limit = ref(10)
const drawer = ref(false)
const focusRow = ref(0)
const listMode = ref<'watch' | 'all'>('watch')

const run = computed(() => props.sample.run.value)
const rows = computed(() => props.sample.state.value.rows)
const items = computed(() => rows.value?.items ?? [])
const compare = computed(() => props.sample.state.value.compare)
const running = computed(() => props.sample.running.value)
const workerOffline = computed(() => props.sample.workerOffline.value)
const maxRows = computed(() => Math.min(MAX_ROWS, props.template?.excel_rows ?? 0))
const limitLocked = computed(() => running.value || !maxRows.value)
const watched = computed(() => rowsToWatch(items.value))
const displayedRows = computed(() => (listMode.value === 'watch' && watched.value.length > 0 ? watched.value : items.value))
const notes = computed(() => new Map(items.value.map(row => [row.row, rowNote(row, rows.value?.fields ?? [])])))
const compared = computed(() => compare.value?.fixed !== undefined)

const stale = computed(() => Boolean(run.value && props.template && !sampleCurrent(run.value, props.template)))
const retryable = computed(() => Boolean(props.canRun && run.value?.can_retry && !stale.value))
const noFields = computed(() => {
  const tpl = props.template
  return tpl && tpl.content.trim() ? missingFieldsWarning(tpl.content, tpl.fields) : ''
})

function computeBlocker(tpl: PromptTemplate | null, dirty: boolean, model: AiModel | undefined): string {
  if (!tpl?.excel_name) return '请先绑定测试样本 Excel（政策类可在上方配置栏「从政策库取数」）'
  if (dirty) return '当前草稿有未保存的修改，请先保存后再试跑'
  if (!tpl.content.trim()) return '提示词内容为空，编写并保存后再试跑'
  if (!tpl.model_id) return '请先在左上方配置栏选择模型并保存'
  if (!model?.available) return `「${tpl.model_name}」暂不可用，请切换其他可用模型`
  return ''
}

const blocker = computed(() => computeBlocker(props.template, props.dirty, props.model))
const allGood = computed(() => {
  if (!run.value || running.value || !items.value.length || watched.value.length) return ''
  return compared.value ? `全部 ${items.value.length} 行均解析成功，且与上次试跑结果一致。` : `全部 ${items.value.length} 行均按输出字段解析成功。`
})

watch(() => props.template?.id, () => {
  limit.value = Math.min(10, maxRows.value || 10)
  listMode.value = 'watch'
})
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
    <div class="sample__launch">
      <p
        class="sample__source"
        :title="template?.excel_name"
      >
        <template v-if="template?.excel_name">
          <strong>{{ template.excel_name }}</strong><span>共 {{ template.excel_rows }} 行</span>
        </template>
        <template v-else>
          未绑定测试样本
        </template>
      </p>
      <div
        v-if="canRun"
        class="sample__controls"
      >
        <label for="sample-limit">跑前</label>
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

    <div class="sample__scroll">
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
        {{ blocker || `用保存的草稿和「${model?.name}」逐条提问，按条计费，单次最多 ${MAX_ROWS} 条` }}
        <el-button
          v-if="!template?.excel_name"
          link
          type="primary"
          size="small"
          @click="emit('upload')"
        >
          上传样本
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
          <span class="sample__meta">{{ shortTime(run.created_at) }} · {{ run.created_by_name }}</span>
          <span class="sample__cost">{{ formatYuan(run.inference_cost + run.search_cost) }}</span>
        </div>
        <el-progress
          v-if="running"
          :percentage="run.percent"
          :show-text="false"
          :stroke-width="4"
        />
        <SampleStrip
          v-if="items.length"
          :rows="items"
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
          草稿在这次试跑之后改过，结果可能过时，点「再跑一次」验证新版效果
        </p>
      </section>

      <SamplePreviewTable
        v-if="wide && rows && items.length && !running"
        :columns="rows.columns"
        :fields="rows.fields"
        :items="items"
        :can-run="canRun"
        :active-row="activeRow"
        @pick="open"
        @trial="row => emit('trial', row)"
      />

      <template v-else-if="items.length && !running">
        <div class="sample__list-bar">
          <el-radio-group
            v-model="listMode"
            size="small"
            class="ai-seg"
            aria-label="筛选试跑行"
          >
            <el-radio-button value="watch">
              需关注 {{ watched.length }}
            </el-radio-button>
            <el-radio-button value="all">
              全部 {{ items.length }}
            </el-radio-button>
          </el-radio-group>
          <button
            type="button"
            class="sample__matrix-link"
            @click="open()"
          >
            多列宽表对照 ↗
          </button>
        </div>

        <p
          v-if="listMode === 'watch' && allGood"
          class="sample__good"
        >
          {{ allGood }}
        </p>

        <ul
          v-else
          class="sample__items"
          aria-label="样本试跑逐行摘要"
        >
          <li
            v-for="row in displayedRows"
            :key="row.row"
            class="sample__item"
            @click="open(row.row)"
          >
            <button
              type="button"
              class="sample__no"
              :class="`is-${row.status}`"
              :aria-label="`看第 ${row.row} 行`"
              @click.stop="open(row.row)"
            >
              {{ row.row }}
            </button>
            <div class="sample__text">
              <p
                class="sample__title"
                :title="title(row)"
              >
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
              type="primary"
              plain
              @click.stop="emit('trial', row.row)"
            >
              单行调试
            </el-button>
          </li>
        </ul>
      </template>

      <p
        v-if="!run && !sample.loading.value"
        class="sample__empty"
      >
        试发一次问一行。上线前用测试样本整批跑一遍，逐行看解析出的字段与上次对比差异。
      </p>
    </div>

    <footer
      v-if="run"
      class="sample__foot"
    >
      <el-button
        type="primary"
        size="small"
        @click="open()"
      >
        逐行对比 ({{ items.length }})
      </el-button>
      <el-button
        v-if="canExport && run.files.result"
        size="small"
        @click="sample.download"
      >
        下载 Excel
      </el-button>
      <span class="sample__spacer" />
      <el-button
        v-if="retryable"
        size="small"
        title="用这次的提示词重问失败和没跑到的行"
        :loading="sample.busy.value"
        @click="sample.retry"
      >
        重跑失败 ({{ run.pending_count }})
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

<style scoped src="./sample-run-panel.css"></style>
