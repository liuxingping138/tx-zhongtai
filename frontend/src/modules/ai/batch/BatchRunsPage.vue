<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'

import { batchOptions, listBatchRuns, startBatchRun, type AiModel, type BatchRun, type PromptTemplate } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import ModelPicker from '../shared/ModelPicker.vue'
import { isActive } from '../shared/aiText'
import BatchHistory from './BatchHistory.vue'
import '../shared/ai.css'

const POLL_MS = 2000
const TEST_ROWS = 10
const auth = useAuthStore()
const canRun = computed(() => auth.canFull('ai.batch_runs'))
const canExport = computed(() => auth.canExport('ai.batch_runs'))
const templates = ref<PromptTemplate[]>([])
const models = ref<AiModel[]>([])
const selectedId = ref('')
const keyword = ref('')
const fallbackModel = ref('')
const thinking = ref(false)
const starting = ref(false)
const runs = ref<BatchRun[]>([])
const total = ref(0)
const page = ref(1)
const loadingRuns = ref(false)
const loadError = ref('')
let timer: number | undefined

const selected = computed(() => templates.value.find(item => item.id === selectedId.value) ?? null)
const visibleTemplates = computed(() => {
  const needle = keyword.value.trim()
  return needle ? templates.value.filter(item => item.title.includes(needle)) : templates.value
})
/** 模板配了模型就用模板的，没配才用页面上选的。 */
const runModelId = computed(() => selected.value?.model_id || fallbackModel.value)
const runModel = computed(() => models.value.find(item => item.id === runModelId.value))
const runningForSelected = computed(() => runs.value.some(run => run.prompt_id === selectedId.value && isActive(run.status)))
const blocker = computed(() => {
  if (!selected.value) return '先在左侧选择一个模板'
  if (!selected.value.excel_name) return '该模板还没有上传 Excel，请先到「提问配置」上传'
  if (!runModel.value) return selected.value.model_id ? `模板配置的模型「${selected.value.model_id}」已不可用，请到「提问配置」改选` : '请选择运行使用的模型'
  if (!runModel.value.available) return `${runModel.value.name} 的接口密钥未配置，暂不能运行`
  if (runningForSelected.value) return '该模板已有任务在运行，结束或停止后才能再次发起'
  return ''
})

async function loadOptions(): Promise<void> {
  try {
    const data = await batchOptions()
    templates.value = data.templates
    models.value = data.models
    fallbackModel.value ||= data.models.find(item => item.available)?.id ?? ''
  } catch (error) {
    loadError.value = errorMessage(error, '模板加载失败，请刷新重试')
  }
}

async function loadRuns(quiet = false): Promise<void> {
  loadingRuns.value = !quiet
  try {
    const data = await listBatchRuns(page.value)
    runs.value = data.items
    total.value = data.total
  } catch (error) {
    if (!quiet) ElMessage.error(errorMessage(error, '历史记录加载失败，请重试'))
  } finally {
    loadingRuns.value = false
    schedule()
  }
}

/** 有任务在排队或运行时每 2 秒刷新一次进度，全部结束后停止轮询。 */
function schedule(): void {
  window.clearTimeout(timer)
  if (runs.value.some(run => isActive(run.status))) timer = window.setTimeout(() => void loadRuns(true), POLL_MS)
}

watch(page, () => void loadRuns())
onMounted(() => {
  void loadOptions()
  void loadRuns()
})
onBeforeUnmount(() => window.clearTimeout(timer))

async function start(limit: number): Promise<void> {
  const template = selected.value
  if (!template || blocker.value) return
  const rows = limit ? Math.min(limit, template.excel_rows) : template.excel_rows
  if (!limit) {
    const ok = await ElMessageBox.confirm(`将用「${runModel.value?.name}」逐行提问 ${rows} 条，会产生模型费用。建议先运行 ${TEST_ROWS} 条测试确认效果。`, '运行全部？', {
      type: 'warning', confirmButtonText: '开始运行', cancelButtonText: '取消',
    }).then(() => true, () => false)
    if (!ok) return
  }
  starting.value = true
  try {
    const useThinking = thinking.value && Boolean(runModel.value?.supports_thinking)
    await startBatchRun({ prompt_id: template.id, model_id: runModelId.value, thinking: useThinking, limit })
    ElMessage.success(`已加入队列，共 ${rows} 条`)
    page.value = 1
    await loadRuns()
  } catch (error) {
    ElMessage.error(errorMessage(error, '发起失败，请重试'))
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <section class="batch">
    <h1 class="ai-sr-only">
      批量提问
    </h1>
    <div class="batch__top">
      <div class="ai-panel batch__templates">
        <div class="ai-panel__head">
          <h2>选择模板</h2>
        </div>
        <div class="batch__search">
          <el-input
            v-model="keyword"
            :prefix-icon="Search"
            clearable
            placeholder="按标题查找"
            aria-label="按标题查找模板"
          />
        </div>
        <el-alert
          v-if="loadError"
          :title="loadError"
          type="error"
          :closable="false"
          show-icon
        />
        <ul
          class="ai-template-list"
          aria-label="提示词模板"
        >
          <li v-if="!visibleTemplates.length">
            <p class="ai-panel__hint batch__empty">
              {{ templates.length ? '没有匹配的模板' : '还没有模板，请先到「提问配置」新建' }}
            </p>
          </li>
          <li
            v-for="item in visibleTemplates"
            :key="item.id"
          >
            <button
              type="button"
              :aria-current="item.id === selectedId"
              @click="selectedId = item.id"
            >
              <strong>{{ item.title }}</strong>
              <span>{{ item.excel_name ? `${item.excel_rows} 行` : '未上传 Excel' }} · {{ item.model_name || '未指定模型' }}</span>
            </button>
          </li>
        </ul>
      </div>

      <div class="ai-panel batch__detail">
        <div class="ai-panel__head">
          <h2>{{ selected?.title ?? '运行' }}</h2>
        </div>
        <p
          v-if="!selected"
          class="ai-panel__hint batch__placeholder"
        >
          在左侧选择一个模板，这里显示它的 Excel、码表、输出字段和提示词，确认后再运行。
        </p>
        <dl
          v-else
          class="batch__facts"
        >
          <div><dt>Excel</dt><dd>{{ selected.excel_name ? `${selected.excel_name}（${selected.excel_rows} 行）` : '未上传' }}</dd></div>
          <div><dt>码表</dt><dd>{{ selected.code_name || '未上传' }}</dd></div>
          <div><dt>输出字段</dt><dd>{{ selected.fields.join('、') || '未设置（结果表里不会多出解析列）' }}</dd></div>
          <div>
            <dt>提示词</dt><dd class="batch__content">
              {{ selected.content }}
            </dd>
          </div>
        </dl>
        <div class="batch__run">
          <ModelPicker
            v-if="selected && !selected.model_id"
            v-model="fallbackModel"
            v-model:thinking="thinking"
            :models="models"
          />
          <p
            v-else-if="runModel"
            class="ai-panel__hint"
          >
            使用模板配置的模型：{{ runModel.name }}
            <el-switch
              v-if="runModel.supports_thinking"
              v-model="thinking"
              active-text="深度思考"
              class="batch__thinking"
            />
          </p>
          <p
            v-if="blocker"
            class="ai-panel__hint batch__blocker"
          >
            {{ blocker }}
          </p>
          <div
            v-if="canRun"
            class="batch__actions"
          >
            <el-button
              :disabled="Boolean(blocker)"
              :loading="starting"
              @click="start(TEST_ROWS)"
            >
              运行 {{ TEST_ROWS }} 条测试
            </el-button>
            <el-button
              type="primary"
              :disabled="Boolean(blocker)"
              :loading="starting"
              @click="start(0)"
            >
              运行全部
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <div class="ai-panel batch__history">
      <div class="ai-panel__head">
        <h2>批量提问历史</h2>
        <el-button
          size="small"
          :icon="Refresh"
          :loading="loadingRuns"
          @click="loadRuns()"
        >
          刷新
        </el-button>
      </div>
      <BatchHistory
        v-model:page="page"
        :items="runs"
        :total="total"
        :loading="loadingRuns"
        :can-run="canRun"
        :can-export="canExport"
        @changed="loadRuns()"
      />
    </div>
  </section>
</template>

<style scoped>
.batch { display: flex; flex-direction: column; gap: 16px; }
/* 上面是选模板和看详情，并排占满整行；历史在下面，整页纵向滚动。 */
.batch__top { display: grid; grid-template-columns: minmax(280px, 360px) minmax(0, 1fr); gap: 16px; height: clamp(440px, 56vh, 600px); }
.batch__templates, .batch__detail { display: flex; flex-direction: column; min-height: 0; }
.batch__templates .ai-template-list { flex: 1; min-height: 0; }
.batch__search { padding: 10px 12px 0; }
.batch__empty { padding: 16px 8px; }
.batch__placeholder { flex: 1; display: grid; place-items: center; padding: 24px; text-align: center; }
.batch__facts { flex: 1; min-height: 0; display: grid; grid-template-rows: auto auto auto minmax(0, 1fr); gap: 10px; margin: 0; padding: 14px 16px 0; font-size: 13px; }
.batch__facts div { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 8px; min-height: 0; }
.batch__facts dt { color: var(--zt-ink-500); }
.batch__facts dd { margin: 0; color: var(--zt-ink-900); word-break: break-word; }
.batch__content { min-height: 0; overflow: auto; white-space: pre-wrap; padding: 8px 10px; border-radius: 4px; background: var(--zt-soft); line-height: 1.7; }
.batch__run { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 16px; padding: 14px 16px 16px; border-top: 1px solid var(--zt-border); margin-top: 14px; }
.batch__thinking { margin-left: 10px; }
.batch__blocker { color: var(--el-color-warning-dark-2); }
.batch__actions { display: flex; gap: 8px; margin-left: auto; }
.batch__actions .el-button { margin: 0; }
.batch__history { display: flex; flex-direction: column; height: clamp(480px, calc(100dvh - var(--workspace-header-height) - 48px), 820px); }
@media (max-width: 1100px) {
  .batch__top { grid-template-columns: minmax(0, 1fr); height: auto; }
  .batch__templates { height: 320px; }
  .batch__detail { min-height: 420px; }
}
</style>
