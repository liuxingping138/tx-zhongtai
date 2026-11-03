<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'

import { batchOptions, batchRunFilterOptions, getBatchRun, listBatchRuns, type AiModel, type BatchRun, type BatchRunFilters, type PromptTemplate, type TemplateCategory } from '@/api/ai'
import { errorMessage, isApiError } from '@/api/errors'
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
/** 详情抽屉里的任务单独存一份：按「运行中」筛着时任务一结束、点了重跑，它就不在当前页了，抽屉不能跟着关。 */
const viewing = ref<BatchRun | null>(null)
const runs = ref<BatchRun[]>([])
const total = ref(0)
const page = ref(1)
const loadingRuns = ref(false)
const loadError = ref('')
const workerOnline = ref(true)
let timer: number | undefined
let sequence = 0
let disposed = false

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
const canManageViewing = computed(() => Boolean(viewing.value && canRun.value && editableCategories.value.includes(viewing.value.prompt_category)))

/** 每次新建都重取模板：页面开着时别人上线了新版本、新建了模板，下拉和「线上第几版」要跟上。 */
function openNew(): void {
  creating.value = true
  void loadOptions()
}

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

/** 只认最后一次请求的结果：翻页、筛选、轮询的请求可能后发先回，旧结果不能盖掉新的。 */
async function loadRuns(quiet = false): Promise<void> {
  const ticket = ++sequence
  loadingRuns.value = !quiet
  try {
    const data = await listBatchRuns(page.value, undefined, applied.value)
    if (ticket !== sequence) return
    runs.value = data.items
    total.value = data.total
    workerOnline.value = data.worker_online
    await refreshViewing()
  } catch (error) {
    if (ticket === sequence && !quiet) ElMessage.error(errorMessage(error, '任务加载失败，请重试'))
  } finally {
    if (ticket === sequence) {
      loadingRuns.value = false
      schedule()
    }
  }
}

/** 抽屉里的任务跟着刷新：在这一页就用列表里的，不在就单独取一次；取不到（被删了）才关抽屉。 */
async function refreshViewing(): Promise<void> {
  const current = viewing.value
  if (!current) return
  const listed = runs.value.find(item => item.id === current.id)
  if (listed) {
    viewing.value = listed
    return
  }
  try {
    const fresh = await getBatchRun(current.id)
    if (viewing.value?.id === fresh.id) viewing.value = fresh
  } catch (error) {
    // 只有确实不在了（被删）才关；网络抖一下保留抽屉，下一次刷新再取。
    if (isApiError(error) && error.status === 404 && viewing.value?.id === current.id) viewing.value = null
  }
}

/** 列表或抽屉里有任务在排队、运行时每 2 秒刷新一次进度，全部结束后停止轮询；离开页面后不再排下一次。 */
function schedule(): void {
  window.clearTimeout(timer)
  if (disposed) return
  const active = runs.value.some(run => isActive(run.status)) || (viewing.value !== null && isActive(viewing.value.status))
  if (active) timer = window.setTimeout(() => void loadRuns(true), POLL_MS)
}

watch(page, () => void loadRuns())
onMounted(() => {
  void loadOptions()
  void loadFilterOptions()
  void loadRuns()
})
onBeforeUnmount(() => {
  disposed = true
  window.clearTimeout(timer)
})

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
      <el-alert
        v-if="loadError"
        :title="loadError"
        type="error"
        :closable="false"
        show-icon
      />
      <el-alert
        v-if="!workerOnline"
        title="AI 执行进程不在线：排队中的任务暂时不会开始，运行中的任务也不会有进度。请联系管理员检查 ai-worker。"
        type="warning"
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
      <!-- 和别的列表一样：筛选下面一行写总数，右边是工具栏；页面标题只给读屏 -->
      <div class="batch__toolbar">
        <span class="batch__total">共 <strong>{{ total }}</strong> 个任务</span>
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
            @click="openNew"
          >
            新建批量任务
          </el-button>
        </div>
      </div>
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
        @open="run => viewing = run"
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
      @close="viewing = null"
    />
  </section>
</template>

<style scoped>
.batch { height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 520px; }
.batch__panel { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.batch__toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 16px; }
.batch__total { color: var(--zt-ink-700); font-size: 14px; font-variant-numeric: tabular-nums; }
.batch__total strong { margin: 0 2px; color: var(--zt-ink-900); font-size: 16px; }
.batch__tools { display: flex; gap: 8px; }
.batch__tools .el-button { margin: 0; }
.batch__filters { padding: 12px 16px; border-bottom: 1px solid var(--zt-border); }
</style>
