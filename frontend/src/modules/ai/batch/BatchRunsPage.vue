<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

import { batchOptions, batchRunFilterOptions, listBatchRuns, startBatchRun, type AiModel, type BatchRun, type BatchRunFilters, type PromptTemplate, type TemplateCategory } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import { useAuthStore } from '@/stores/auth'
import { RUN_MODE_TEXT, RUN_STATUS_TEXT, isActive } from '../shared/aiText'
import TemplatePicker from '../shared/TemplatePicker.vue'
import BatchHistory from './BatchHistory.vue'
import RunCard from './RunCard.vue'
import '../shared/ai.css'

const POLL_MS = 2000
const TEST_ROWS = 10
const auth = useAuthStore()
const canRun = computed(() => auth.canFull('ai.batch_runs'))
const canExport = computed(() => auth.canExport('ai.batch_runs'))
const templates = ref<PromptTemplate[]>([])
const models = ref<AiModel[]>([])
const categories = ref<TemplateCategory[]>([])
const editableCategories = computed(() => categories.value.filter(item => item.editable).map(item => item.code))
const categoryLabels = computed(() => Object.fromEntries(categories.value.map(item => [item.code, item.name])))
const selectedId = ref('')
const fallbackModel = ref('')
const thinking = ref(false)
const starting = ref(false)
const runs = ref<BatchRun[]>([])
const total = ref(0)
const page = ref(1)
const loadingRuns = ref(false)
const loadError = ref('')
let timer: number | undefined

type HistoryFilters = Required<BatchRunFilters>
const emptyFilters = (): HistoryFilters => ({ prompt_title: [], prompt_category: [], created_by_name: [], run_mode: [], status: [] })
/** query 是正在填的条件，applied 是点「查询」后生效的条件；翻页和轮询都只用 applied。 */
const query = reactive<HistoryFilters>(emptyFilters())
const applied = ref<HistoryFilters>(emptyFilters())
const filterOptions = ref<{ prompt_title: string[]; created_by_name: string[] }>({ prompt_title: [], created_by_name: [] })
const RUN_MODE_OPTIONS = Object.keys(RUN_MODE_TEXT)
const STATUS_OPTIONS = Object.keys(RUN_STATUS_TEXT)
const filtered = computed(() => Object.values(applied.value).some(values => values.length > 0))

const selected = computed(() => templates.value.find(item => item.id === selectedId.value) ?? null)
/** 模板配了模型就用模板的，没配才用页面上选的。 */
const runModelId = computed(() => selected.value?.model_id || fallbackModel.value)
const runModel = computed(() => models.value.find(item => item.id === runModelId.value))
const runningForSelected = computed(() => runs.value.some(run => run.prompt_id === selectedId.value && isActive(run.status)))
const blocker = computed(() => {
  if (!selected.value) return '先在左侧选择一个模板'
  if (!selected.value.editable) return `你对「${selected.value.category_name}」类模板只有查看权限，不能运行`
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
    categories.value = data.categories
    fallbackModel.value ||= data.models.find(item => item.available)?.id ?? ''
  } catch (error) {
    loadError.value = errorMessage(error, '模板加载失败，请刷新重试')
  }
}

async function loadFilterOptions(): Promise<void> {
  try {
    filterOptions.value = await batchRunFilterOptions()
  } catch {
    // 候选值拿不到时下拉为空，仍可手动输入后回车
  }
}

function search(): void {
  applied.value = {
    prompt_title: [...query.prompt_title],
    prompt_category: [...query.prompt_category],
    created_by_name: [...query.created_by_name],
    run_mode: [...query.run_mode],
    status: [...query.status],
  }
  void reloadFromFirstPage()
}

/** 已在第一页就直接重新加载，否则改页码交给 watch(page) 加载，避免同一次刷新请求两遍。 */
async function reloadFromFirstPage(): Promise<void> {
  if (page.value === 1) await loadRuns()
  else page.value = 1
}

function resetFilters(): void {
  Object.assign(query, emptyFilters())
  search()
}

async function loadRuns(quiet = false): Promise<void> {
  loadingRuns.value = !quiet
  try {
    const data = await listBatchRuns(page.value, undefined, applied.value)
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
  void loadFilterOptions()
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
    void loadFilterOptions()
    await reloadFromFirstPage()
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
    <aside class="ai-panel batch__rail">
      <div class="ai-panel__head">
        <h2>模板</h2>
      </div>
      <TemplatePicker
        :templates="templates"
        :categories="categories"
        :selected-id="selectedId"
        :error="loadError"
        empty-text="还没有模板，先到「提问配置」新建"
        @select="item => selectedId = item.id"
      >
        <template #meta="{ item }">
          {{ item.excel_name ? `${item.excel_rows} 行` : '未上传 Excel' }}
        </template>
      </TemplatePicker>
    </aside>

    <div class="batch__main">
      <RunCard
        v-model:fallback-model="fallbackModel"
        v-model:thinking="thinking"
        :template="selected"
        :models="models"
        :run-model="runModel"
        :blocker="selected ? blocker : ''"
        :can-run="canRun"
        :starting="starting"
        :test-rows="TEST_ROWS"
        @start="start"
      />

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
        <FilterBar
          class="batch__filters"
          :query="query"
          :applied="applied"
          @search="search"
          @reset="resetFilters"
        >
          <el-form-item label="模板名称">
            <FilterSelect
              v-model="query.prompt_title"
              :options="filterOptions.prompt_title"
              placeholder="输入或选择模板"
            />
          </el-form-item>
          <el-form-item label="模板类型">
            <FilterSelect
              v-model="query.prompt_category"
              :options="categories.map(item => item.code)"
              :labels="categoryLabels"
              placeholder="全部"
              size="short"
            />
          </el-form-item>
          <el-form-item label="运行方式">
            <FilterSelect
              v-model="query.run_mode"
              :options="RUN_MODE_OPTIONS"
              :labels="RUN_MODE_TEXT"
              placeholder="全部"
              size="short"
            />
          </el-form-item>
          <el-form-item label="发起人">
            <FilterSelect
              v-model="query.created_by_name"
              :options="filterOptions.created_by_name"
              placeholder="输入或选择发起人"
              size="short"
            />
          </el-form-item>
          <el-form-item label="状态">
            <FilterSelect
              v-model="query.status"
              :options="STATUS_OPTIONS"
              :labels="RUN_STATUS_TEXT"
              placeholder="全部"
              size="short"
            />
          </el-form-item>
        </FilterBar>
        <BatchHistory
          v-model:page="page"
          :filtered="filtered"
          :items="runs"
          :total="total"
          :loading="loadingRuns"
          :can-run="canRun"
          :can-export="canExport"
          :editable-categories="editableCategories"
          @changed="loadRuns()"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 左边模板整列；右边上方运行卡、下方历史，整页纵向滚动时模板列停在原位。 */
.batch { display: grid; grid-template-columns: 248px minmax(0, 1fr); align-items: start; gap: 12px; }
.batch__rail { display: flex; flex-direction: column; position: sticky; top: 0; height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 420px; overflow: hidden; }
.batch__main { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.batch__filters { padding: 12px 16px; border-bottom: 1px solid var(--zt-border); }
.batch__history { display: flex; flex-direction: column; height: clamp(480px, calc(100dvh - var(--workspace-header-height) - 48px), 820px); }
@media (max-width: 960px) {
  .batch { grid-template-columns: minmax(0, 1fr); }
  .batch__rail { position: static; height: 320px; }
}
</style>
