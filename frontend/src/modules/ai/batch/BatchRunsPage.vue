<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'

import { batchOptions, batchRunFilterOptions, listBatchRuns, type AiModel, type BatchRun, type BatchRunFilters, type PromptTemplate, type TemplateCategory } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import { useAuthStore } from '@/stores/auth'
import { RUN_MODE_TEXT, RUN_SOURCE_TEXT, RUN_STATUS_TEXT, isActive } from '../shared/aiText'
import BatchHistory from './BatchHistory.vue'
import BatchRunDrawer from './BatchRunDrawer.vue'
import NewBatchTask from './NewBatchTask.vue'
import '../shared/ai.css'

/** 批量任务：用已上线的模板跑这次上传的数据，定时任务发起的也在这里。主页是任务列表，新建和详情都在抽屉里。 */
const POLL_MS = 2000
const auth = useAuthStore()
const canRun = computed(() => auth.canFull('ai.batch_runs'))
const canExport = computed(() => auth.canExport('ai.batch_runs'))
const templates = ref<PromptTemplate[]>([])
const models = ref<AiModel[]>([])
const categories = ref<TemplateCategory[]>([])
const editableCategories = computed(() => categories.value.filter(item => item.editable).map(item => item.code))
const categoryLabels = computed(() => Object.fromEntries(categories.value.map(item => [item.code, item.name])))
const creating = ref(false)
const viewingId = ref('')
const runs = ref<BatchRun[]>([])
const total = ref(0)
const page = ref(1)
const loadingRuns = ref(false)
const loadError = ref('')
let timer: number | undefined

type HistoryFilters = Required<BatchRunFilters>
const emptyFilters = (): HistoryFilters => ({ prompt_title: [], prompt_category: [], source: [], run_mode: [], status: [], created_by_name: [] })
/** query 是正在填的条件，applied 是点「查询」后生效的条件；翻页和轮询都只用 applied。 */
const query = reactive<HistoryFilters>(emptyFilters())
const applied = ref<HistoryFilters>(emptyFilters())
const filterOptions = ref<{ prompt_title: string[]; created_by_name: string[] }>({ prompt_title: [], created_by_name: [] })
const RUN_MODE_OPTIONS = Object.keys(RUN_MODE_TEXT)
const SOURCE_OPTIONS = Object.keys(RUN_SOURCE_TEXT)
const STATUS_OPTIONS = Object.keys(RUN_STATUS_TEXT)
const filtered = computed(() => Object.values(applied.value).some(values => values.length > 0))
const viewing = computed(() => runs.value.find(item => item.id === viewingId.value) ?? null)
const canManageViewing = computed(() => Boolean(viewing.value && canRun.value && editableCategories.value.includes(viewing.value.prompt_category)))

async function loadOptions(): Promise<void> {
  try {
    const data = await batchOptions()
    templates.value = data.templates
    models.value = data.models
    categories.value = data.categories
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
  applied.value = Object.fromEntries(Object.entries(query).map(([key, values]) => [key, [...values]])) as HistoryFilters
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
    // 详情里的任务被删了、或者翻页后不在这一页了，关掉抽屉。
    if (viewingId.value && !viewing.value) viewingId.value = ''
  } catch (error) {
    if (!quiet) ElMessage.error(errorMessage(error, '任务加载失败，请重试'))
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

async function created(): Promise<void> {
  void loadFilterOptions()
  await reloadFromFirstPage()
}
</script>

<template>
  <section class="batch">
    <h1 class="ai-sr-only">
      批量任务
    </h1>
    <div class="ai-panel batch__panel">
      <div class="ai-panel__head">
        <h2>批量任务</h2>
        <div class="batch__tools">
          <el-button
            :icon="Refresh"
            :loading="loadingRuns"
            @click="loadRuns()"
          >
            刷新
          </el-button>
          <el-button
            v-if="canRun && editableCategories.length"
            type="primary"
            :icon="Plus"
            @click="creating = true"
          >
            新建批量任务
          </el-button>
        </div>
      </div>
      <el-alert
        v-if="loadError"
        :title="loadError"
        type="error"
        :closable="false"
        show-icon
      />
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
        <el-form-item label="来源">
          <FilterSelect
            v-model="query.source"
            :options="SOURCE_OPTIONS"
            :labels="RUN_SOURCE_TEXT"
            placeholder="全部"
            size="short"
          />
        </el-form-item>
        <el-form-item label="运行范围">
          <FilterSelect
            v-model="query.run_mode"
            :options="RUN_MODE_OPTIONS"
            :labels="RUN_MODE_TEXT"
            placeholder="全部"
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
        <el-form-item label="发起人">
          <FilterSelect
            v-model="query.created_by_name"
            :options="filterOptions.created_by_name"
            placeholder="输入或选择发起人"
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
        @open="run => viewingId = run.id"
      />
    </div>
    <NewBatchTask
      v-model="creating"
      :templates="templates"
      :models="models"
      @created="created"
    />
    <BatchRunDrawer
      :run="viewing"
      :can-manage="canManageViewing"
      :can-export="canExport"
      @changed="loadRuns(true)"
      @close="viewingId = ''"
    />
  </section>
</template>

<style scoped>
.batch { height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 520px; }
.batch__panel { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.batch__tools { display: flex; gap: 8px; }
.batch__tools .el-button { margin: 0; }
.batch__filters { padding: 12px 16px; border-bottom: 1px solid var(--zt-border); }
</style>
