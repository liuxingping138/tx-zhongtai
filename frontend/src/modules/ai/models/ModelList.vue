<script setup lang="ts">
import { Plus, Search } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { listModelConfigs, updateModelConfig, type ModelConfig } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import AuditLogButton from '@/components/AuditLogButton.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import ModelDetailDrawer from './ModelDetailDrawer.vue'
import ModelEditorDrawer from './ModelEditorDrawer.vue'
import ModelTable from './ModelTable.vue'
import { draftFromModel, draftToBody } from './modelDraft'
import {
  benchmarkSummary,
  filterModels,
  providerReadyState,
  type ModelFilters,
  type ModelSortKey,
  type PriceUnit,
} from './modelView'
import '../shared/ai.css'
import './model-list.css'

const RESOURCE = 'ai.models'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))

const items = ref<ModelConfig[]>([])
const loading = ref(false)
const loadError = ref('')
const toggling = ref('')
const unit = ref<PriceUnit>('million')
const sortKey = ref<ModelSortKey>('sort_order')
const sortAsc = ref(true)
const viewingId = ref('')
const editorOpen = ref(false)
const editingModel = ref<ModelConfig | null>(null)

const filters = reactive<ModelFilters>({
  provider: 'all',
  status: 'all',
  webOnly: false,
  keyword: '',
})

const viewingModel = computed(() => items.value.find(item => item.id === viewingId.value) ?? null)
const rows = computed(() => filterModels(items.value, filters, sortKey.value, sortAsc.value))
const hasFilters = computed(() => Boolean(
  filters.provider !== 'all' || filters.status !== 'all' || filters.webOnly || filters.keyword.trim(),
))

const stats = computed(() => {
  const all = items.value
  const enabled = all.filter(item => item.enabled).length
  const ark = all.filter(item => item.provider === 'ark').length
  const baidu = all.filter(item => item.provider === 'baidu').length
  const web = all.filter(item => item.web_search).length
  return { total: all.length, enabled, disabled: all.length - enabled, ark, baidu, web }
})

const arkReady = computed(() => providerReadyState(items.value, 'ark'))
const baiduReady = computed(() => providerReadyState(items.value, 'baidu'))
const benchmark = computed(() => benchmarkSummary(items.value))

async function load(): Promise<void> {
  loading.value = true
  try {
    items.value = await listModelConfigs()
    loadError.value = ''
  } catch (error) {
    loadError.value = errorMessage(error, '加载模型配置失败')
  } finally {
    loading.value = false
  }
}

function toggleSort(nextKey: ModelSortKey): void {
  if (sortKey.value === nextKey) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = nextKey
    sortAsc.value = true
  }
}

function resetFilters(): void {
  filters.provider = 'all'
  filters.status = 'all'
  filters.webOnly = false
  filters.keyword = ''
}

function openDetail(row: ModelConfig): void {
  viewingId.value = row.id
}

function openCreate(): void {
  viewingId.value = ''
  editingModel.value = null
  editorOpen.value = true
}

function openEdit(row: ModelConfig): void {
  viewingId.value = ''
  editingModel.value = row
  editorOpen.value = true
}

async function copyText(value: string, label: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value)
    ElMessage.success(`已复制${label}：${value}`)
  } catch {
    ElMessage.info(`${label}：${value}`)
  }
}

async function toggle(row: ModelConfig): Promise<void> {
  if (toggling.value) return
  const enable = !row.enabled
  const verb = enable ? '启用' : '停用'
  const message = enable
    ? `启用后「${row.name}」会立即出现在提示词模板和批量任务的模型下拉里。`
    : `停用后「${row.name}」不再出现在模型下拉里，已排队或运行中的批量任务照常跑完。`
  const ok = await ElMessageBox.confirm(message, `${verb}这个模型？`, {
    confirmButtonText: verb,
    cancelButtonText: '取消',
    type: 'warning',
  }).then(() => true, () => false)
  if (!ok) return

  toggling.value = row.id
  try {
    const body = draftToBody(draftFromModel(row))
    await updateModelConfig(row.id, { ...body, enabled: enable, id: row.id, version: row.version })
    ElMessage.success(`已${verb}「${row.name}」`)
  } catch (error) {
    ElMessage.error(errorMessage(error, `${verb}失败，请刷新后重试`))
  } finally {
    toggling.value = ''
    await load()
  }
}

onMounted(() => { void load() })
</script>

<template>
  <section
    class="models-page"
    aria-label="模型配置"
  >
    <h1 class="ai-sr-only">
      模型配置
    </h1>

    <!-- A. 顶部紧凑通道与计价健康概览条 -->
    <div class="models-kpi">
      <div class="models-kpi__item is-hero">
        <div class="models-kpi__body">
          <div class="models-kpi__label">
            已配置模型
          </div>
          <div class="models-kpi__val-row models-mono">
            <span class="models-kpi__big">{{ stats.total }}</span>
            <span class="models-kpi__sub-muted">启用 {{ stats.enabled }} · 停用 {{ stats.disabled }}</span>
          </div>
        </div>
        <span class="m-pill m-pill--blue">实时生效</span>
      </div>

      <div class="models-kpi__item">
        <div class="models-kpi__body">
          <div class="models-kpi__label">
            字节方舟（火山引擎）
          </div>
          <div class="models-kpi__sub">
            {{ stats.ark }} 个接入点 · 支持低优 flex 与缓存折算
          </div>
        </div>
        <span
          class="m-pill"
          :class="arkReady === 'missing' ? 'm-pill--amber' : 'm-pill--green'"
        >
          <i class="m-pill__dot" />{{ arkReady === 'missing' ? '未配密钥' : '密钥就绪' }}
        </span>
      </div>

      <div class="models-kpi__item">
        <div class="models-kpi__body">
          <div class="models-kpi__label">
            百度千帆（ModelBuilder）
          </div>
          <div class="models-kpi__sub">
            {{ stats.baidu }} 个模型 · 支持提问时切换深度思考
          </div>
        </div>
        <span
          class="m-pill"
          :class="baiduReady === 'missing' ? 'm-pill--amber' : 'm-pill--green'"
        >
          <i class="m-pill__dot" />{{ baiduReady === 'missing' ? '未配密钥' : '密钥就绪' }}
        </span>
      </div>

      <div class="models-kpi__item">
        <div class="models-kpi__body">
          <div class="models-kpi__label">
            主力经济档基准价
          </div>
          <div
            v-if="benchmark"
            class="models-kpi__sub models-mono"
            :title="benchmark.name"
          >
            <strong class="models-kpi__bench">{{ benchmark.pair }}</strong>
            <span class="models-kpi__sub-muted"> {{ benchmark.sub }}</span>
          </div>
          <div
            v-else
            class="models-kpi__sub-muted"
          >
            暂无启用模型
          </div>
        </div>
      </div>
    </div>

    <!-- B. 一体化模型配置主面板 -->
    <div class="ai-panel models-panel">
      <div class="models-toolbar">
        <div class="models-toolbar__left">
          <el-input
            v-model="filters.keyword"
            class="models-search"
            :prefix-icon="Search"
            clearable
            placeholder="搜索名称、ID 或接入点…"
            aria-label="搜索模型名称、ID或接入点"
          />

          <el-radio-group
            v-model="filters.provider"
            class="ai-seg"
            aria-label="按厂商筛选"
          >
            <el-radio-button value="all">
              全部厂商<span class="models-seg-count">{{ stats.total }}</span>
            </el-radio-button>
            <el-radio-button value="ark">
              字节方舟<span class="models-seg-count">{{ stats.ark }}</span>
            </el-radio-button>
            <el-radio-button value="baidu">
              百度千帆<span class="models-seg-count">{{ stats.baidu }}</span>
            </el-radio-button>
          </el-radio-group>

          <el-radio-group
            v-model="filters.status"
            class="ai-seg"
            aria-label="按启停状态筛选"
          >
            <el-radio-button value="all">
              全部<span class="models-seg-count">{{ stats.total }}</span>
            </el-radio-button>
            <el-radio-button value="on">
              启用<span class="models-seg-count">{{ stats.enabled }}</span>
            </el-radio-button>
            <el-radio-button value="off">
              停用<span class="models-seg-count">{{ stats.disabled }}</span>
            </el-radio-button>
          </el-radio-group>

          <button
            type="button"
            class="models-web-toggle"
            :class="{ 'is-active': filters.webOnly }"
            :aria-pressed="filters.webOnly"
            @click="filters.webOnly = !filters.webOnly"
          >
            <span>支持联网</span>
            <span class="models-seg-count">{{ stats.web }}</span>
          </button>
        </div>

        <div class="models-toolbar__right">
          <el-radio-group
            v-model="unit"
            size="small"
            class="ai-seg"
            aria-label="单价展示单位"
          >
            <el-radio-button value="million">
              ¥ / 百万 token
            </el-radio-button>
            <el-radio-button value="thousand">
              元 / 千 token（原值）
            </el-radio-button>
          </el-radio-group>

          <AuditLogButton :module="RESOURCE" />

          <el-button
            v-if="canWrite"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新增模型
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="loadError"
        :title="loadError"
        type="error"
        show-icon
        :closable="false"
      >
        <el-button
          size="small"
          @click="load"
        >
          重试
        </el-button>
      </el-alert>

      <TableSkeleton
        v-else-if="loading && !items.length"
        :rows="6"
      />

      <ModelTable
        v-else
        :rows="rows"
        :unit="unit"
        :can-write="canWrite"
        :toggling="toggling"
        :has-filters="hasFilters"
        :sort-key="sortKey"
        :sort-asc="sortAsc"
        @view="openDetail"
        @edit="openEdit"
        @toggle="toggle"
        @copy="copyText"
        @sort="toggleSort"
        @reset-filters="resetFilters"
      />

      <footer class="models-footer">
        <span>计费优先级：低优档按低优价 → 配置了高峰价的工作日高峰时段按高峰价 → 其余时段按常规价；命中上下文缓存的部分独立按缓存单价折算。</span>
        <span class="models-mono">保存后新提问立即生效 · 运行中批量任务按开跑时快照计费</span>
      </footer>
    </div>

    <ModelDetailDrawer
      :model="viewingModel"
      :can-write="canWrite"
      @close="viewingId = ''"
      @edit="openEdit"
      @copy="copyText"
    />

    <ModelEditorDrawer
      v-model:visible="editorOpen"
      :editing="editingModel"
      :ark-ready="arkReady"
      :baidu-ready="baiduReady"
      @saved="load"
      @conflict="load"
    />
  </section>
</template>
