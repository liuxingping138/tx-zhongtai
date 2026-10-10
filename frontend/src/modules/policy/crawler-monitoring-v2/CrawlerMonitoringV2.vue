<script setup lang="ts">
import { ArrowDown, ArrowUp, Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import {
  CRAWLER_V2_BASE,
  getCrawlerV2Overview,
  listCrawlerSites,
  type CrawlerSiteItem,
  type CrawlerV2Overview,
  type SiteStatus,
} from '@/api/crawlerMonitoringV2'
import { downloadFile } from '@/api/download'
import { errorMessage } from '@/api/errors'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import ListPage from '@/components/ListPage.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useAuthStore } from '@/stores/auth'
import { filtersForExport, toggleValue, useListQuery } from '@/composables/useListQuery'
import { compactCount, siteFilters, STATUS_BY_LABEL, statusValues } from './filters'

const LIST_ERROR = '暂时无法获取网站列表，请稍后重新加载。'
const auth = useAuthStore()
/** 导出单独一档：只读角色能看不能导，按钮保留但禁用并说明原因。 */
const canExport = computed(() => auth.canExport('policy.crawler_monitoring_v2'))
const OVERVIEW_ERROR = '暂时无法获取采集概况，请稍后重试。'

const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const items = ref<CrawlerSiteItem[]>([])
const total = ref(0)
const exporting = ref(false)

const overview = ref<CrawlerV2Overview | null>(null)
const overviewLoading = ref(false)
const overviewError = ref('')
const overviewExpanded = ref(true)

const query = reactive({
  site_name: [] as string[],
  province_name: [] as string[],
  city_name: [] as string[],
  status: [] as string[],
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions(`${CRAWLER_V2_BASE}/sites`)
const statusLabels = Object.fromEntries(Object.keys(STATUS_BY_LABEL).map(label => [label, label]))
const listQuery = useListQuery(query, load)

const tableColumns = [
  { prop: 'site_name', label: '网站名称', minWidth: 220, grow: 2 },
  { prop: 'province_name', label: '省份', width: 120 },
  { prop: 'city_name', label: '地市', width: 120 },
  { prop: 'total_rows', label: '数据总量', width: 110 },
  { prop: 'last_created_at', label: '最新入库时间', width: 170 },
  { prop: 'last_published_date', label: '最近发布时间', width: 120 },
  { prop: 'stale_days', label: '停更天数', width: 100 },
  { prop: 'status_label', label: '状态', width: 90 },
] as const
const columns = computed(() => [...tableColumns])
const defaultColumns = tableColumns.map(column => column.prop)
const selectedColumns = ref<string[]>([...defaultColumns])

const appliedStatuses = computed(() => statusValues(listQuery.applied.status))

const syncNotice = computed(() => {
  const sync = overview.value?.sync
  if (!sync) return ''
  if (sync.status === 'failed') return '最近一次同步失败，统计可能不是最新。请联系管理员检查同步任务。'
  if (sync.status === 'interrupted') return '最近一次同步意外中断，统计可能不完整。请重新执行同步。'
  if (sync.status === 'running') return '数据正在同步，完成后点「刷新统计」即可看到最新结果。'
  if (!sync.last_success_at) return '尚未完成首次同步。完成回填后，这里将显示采集概况。'
  if (sync.outdated) return '统计已超过 36 小时未更新，请检查同步任务。'
  return ''
})

const statusCards = computed(() => {
  const data = overview.value
  if (!data) return []
  const { normal_days: normalDays, watch_days: watchDays } = data.thresholds
  return [
    { status: 'normal' as const, label: '正常', value: data.cards.normal, foot: `${normalDays} 天内有新数据入库` },
    { status: 'watch' as const, label: '关注', value: data.cards.watch, foot: `${normalDays + 1}–${watchDays} 天无新数据` },
    { status: 'stale' as const, label: '停更', value: data.cards.stale, foot: `超过 ${watchDays} 天无新数据` },
  ]
})

let loadSequence = 0

async function load() {
  const params = listQuery.requested()
  void listQuery.commitPage()
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  const filtered = Object.entries(params).some(
    ([key, value]) => !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
  try {
    const page = await listCrawlerSites({ ...siteFilters(params), page: params.page, page_size: params.page_size })
    if (sequence !== loadSequence) return
    items.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    const message = errorMessage(error, LIST_ERROR)
    loadError.value = message === '请求失败' ? LIST_ERROR : message
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

let overviewSequence = 0
async function loadOverview() {
  const sequence = ++overviewSequence
  overviewLoading.value = true
  overviewError.value = ''
  try {
    const result = await getCrawlerV2Overview()
    if (sequence === overviewSequence) overview.value = result
  } catch (error) {
    if (sequence !== overviewSequence) return
    const message = errorMessage(error, OVERVIEW_ERROR)
    overviewError.value = message === '请求失败' ? OVERVIEW_ERROR : message
  } finally {
    if (sequence === overviewSequence) overviewLoading.value = false
  }
}

function onSearch() {
  query.page = 1
  listQuery.captureApplied()
  void load()
}

function onResetFilters() {
  query.site_name = []
  query.province_name = []
  query.city_name = []
  query.status = []
  onSearch()
}

/** 点卡片把该状态加入多选，再次点击移出。以已生效条件为准，未提交的草稿不参与。 */
function pickStatus(status: SiteStatus) {
  const label = Object.entries(STATUS_BY_LABEL).find(([, value]) => value === status)?.[0] ?? ''
  listQuery.replaceApplied('status', toggleValue(listQuery.applied.status, label))
  void load()
}

async function onExport() {
  exporting.value = true
  try {
    await downloadFile(`${CRAWLER_V2_BASE}/sites/export`, '爬虫监测.xlsx', filtersForExport(siteFilters(listQuery.applied)))
    ElMessage.success('下载已开始，请查看浏览器下载列表')
  } catch (error) {
    ElMessage.error(errorMessage(error, '导出失败，请稍后重试'))
  } finally {
    exporting.value = false
  }
}

async function reloadData() {
  await Promise.all([load(), loadOverview(), filters.load()])
}

onMounted(() => { void reloadData() })
const NO_EXPORT_HINT = '你的角色没有导出权限，如需下载 Excel 请联系管理员开通「导出」。'
</script>

<template>
  <div>
    <ListPage
      v-model:page="query.page"
      v-model:page-size="query.page_size"
      title="爬虫监测"
      hint="按网站查看数据总量、最新入库时间与停更天数，停更天数按最新入库日期计算。"
      :loading="loading"
      :error="loadError"
      :total="total"
      @retry="reloadData"
      @change="load"
    >
      <template #actions>
        <el-tooltip
          :content="canExport ? '按当前已生效的筛选条件导出网站明细。' : NO_EXPORT_HINT"
          placement="bottom"
        >
          <span>
            <el-button
              :icon="Download"
              :loading="exporting"
              :disabled="!canExport || loading || !!loadError || total === 0"
              @click="onExport"
            >
              下载 Excel
            </el-button>
          </span>
        </el-tooltip>
      </template>

      <template #summary>
        <div class="overview-heading">
          <div class="overview-caption">
            <h2>采集概况</h2>
            <span
              v-if="overview?.sync.last_success_at"
              class="sync-time"
            >更新于 {{ overview.sync.last_success_at }}</span>
          </div>
          <div class="overview-actions">
            <el-button
              :icon="Refresh"
              text
              :loading="overviewLoading"
              @click="loadOverview"
            >
              刷新统计
            </el-button>
            <el-button
              :icon="overviewExpanded ? ArrowUp : ArrowDown"
              text
              :aria-expanded="overviewExpanded"
              aria-controls="crawler-v2-overview"
              @click="overviewExpanded = !overviewExpanded"
            >
              {{ overviewExpanded ? '收起概览' : '展开概览' }}
            </el-button>
          </div>
        </div>
        <el-alert
          v-if="syncNotice"
          :title="syncNotice"
          :type="['failed', 'interrupted'].includes(overview?.sync.status ?? '') ? 'error' : 'warning'"
          :closable="false"
          show-icon
          class="sync-notice"
        />
        <section
          v-show="overviewExpanded"
          id="crawler-v2-overview"
          v-loading="overviewLoading"
          class="overview"
        >
          <div
            v-if="overviewError"
            class="overview-error"
            role="alert"
          >
            {{ overviewError }}
            <el-button
              link
              type="primary"
              @click="reloadData"
            >
              重试
            </el-button>
          </div>
          <template v-else-if="overview">
            <div class="cards">
              <div class="card">
                <span class="card-label">网站总数</span>
                <strong class="card-value">{{ overview.cards.sites.toLocaleString() }}</strong>
                <span class="card-foot">名称 + 省份 + 地市</span>
              </div>
              <button
                v-for="card in statusCards"
                :key="card.status"
                type="button"
                class="card card-status"
                :class="[`card-${card.status}`, { selected: appliedStatuses.includes(card.status) }]"
                :aria-pressed="appliedStatuses.includes(card.status)"
                :title="appliedStatuses.includes(card.status) ? '再次点击取消筛选' : `筛选${card.label}网站`"
                @click="pickStatus(card.status)"
              >
                <span class="card-label"><span class="dot" />{{ card.label }}</span>
                <strong class="card-value">{{ card.value.toLocaleString() }}</strong>
                <span class="card-foot">{{ card.foot }}</span>
              </button>
              <div class="card">
                <span class="card-label">数据总量</span>
                <strong
                  class="card-value"
                  :title="`${overview.cards.total_rows.toLocaleString()} 条`"
                >{{ compactCount(overview.cards.total_rows) }}</strong>
                <span class="card-foot">不含已删除数据</span>
              </div>
              <div class="card">
                <span class="card-label">昨日采集</span>
                <strong class="card-value">{{ overview.cards.yesterday_rows.toLocaleString() }}</strong>
                <span class="card-foot">按采集日期统计的条数</span>
              </div>
            </div>
          </template>
        </section>
      </template>

      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          @search="onSearch"
          @reset="onResetFilters"
        >
          <el-form-item label="网站名称">
            <FilterSelect
              v-model="query.site_name"
              v-bind="filters.bind('site_name')"
            />
          </el-form-item>
          <el-form-item label="省份">
            <FilterSelect
              v-model="query.province_name"
              v-bind="filters.bind('province_name')"
              size="short"
            />
          </el-form-item>
          <el-form-item label="地市">
            <FilterSelect
              v-model="query.city_name"
              v-bind="filters.bind('city_name')"
              size="short"
            />
          </el-form-item>
          <el-form-item label="状态">
            <FilterSelect
              v-model="query.status"
              v-bind="filters.bind('status')"
              :labels="statusLabels"
              size="short"
            />
          </el-form-item>
        </FilterBar>
      </template>

      <template #tools>
        <ColumnPicker
          v-model="selectedColumns"
          :columns="columns"
          :defaults="defaultColumns"
        />
      </template>

      <BusinessTable
        :items="items"
        :columns="columns"
        :selected="selectedColumns"
        :summary-keys="['status_label', 'stale_days', 'last_created_at']"
        title-key="site_name"
        detail-title="网站详情"
        :can-write="false"
        :loading="loading"
        :filtered="resultFiltered"
        @reset="onResetFilters"
      />
    </ListPage>
  </div>
</template>

<style scoped>
.overview-heading, .overview-caption, .overview-actions { display: flex; align-items: center; gap: 12px; }
.overview-heading { justify-content: space-between; flex-wrap: wrap; margin-bottom: 12px; }
.overview-caption { flex-wrap: wrap; gap: 8px 16px; }
.overview-caption h2 { margin: 0; font-size: 14px; font-weight: 600; color: var(--zt-ink-900); }
.sync-time { color: var(--zt-ink-500); font-size: 12px; font-variant-numeric: tabular-nums; }
.overview-actions { gap: 0; }
.overview-actions .el-button { margin: 0; }
.sync-notice { margin-bottom: 12px; }
.overview { display: flex; flex-direction: column; gap: var(--zt-space-4); margin-bottom: var(--zt-space-4); }
.overview-error { color: var(--zt-ink-700); font-size: 13px; }

.cards { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: var(--zt-space-3); }
.card {
  display: flex; flex-direction: column; gap: 6px; min-height: 110px;
  padding: var(--zt-space-3) var(--zt-space-4);
  background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius);
  font: inherit; text-align: left; color: inherit;
}
.card-status { cursor: pointer; transition: background-color 160ms ease, border-color 160ms ease; }
.card-status:hover { background: var(--zt-soft); }
.card-status:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.card-status.selected { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-5); }
.card-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--zt-ink-700); }
.card-value { font-size: 28px; line-height: 1.2; color: var(--zt-ink-900); font-variant-numeric: tabular-nums; }
.card-foot { font-size: 12px; color: var(--zt-ink-500); }
.dot { width: 8px; height: 8px; border-radius: 2px; flex: none; }
.card-normal .dot { background: var(--el-color-success); }
.card-watch .dot { background: var(--el-color-warning); }
.card-stale .dot { background: var(--el-color-danger); }
.card-stale .card-value { color: var(--el-color-danger); }


@media (max-width: 1280px) {
  .cards { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 767px) {
  .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
