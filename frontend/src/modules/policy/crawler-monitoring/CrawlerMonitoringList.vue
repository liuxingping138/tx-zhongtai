<script setup lang="ts">
import { ArrowDown, ArrowUp, Download, Refresh, Warning } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import {
  getCrawlerOverview,
  listCrawlerTasks,
  type CrawlerOverview,
  type CrawlerTaskItem,
  type HealthStatus,
} from '@/api/crawlerMonitoring'
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
import HealthBar from './HealthBar.vue'
import { crawlerFilters, STATUS_BY_LABEL, statusValues } from './filters'
import TaskTrend from './TaskTrend.vue'
import TrendChart from './TrendChart.vue'

const auth = useAuthStore()
/** 导出单独一档：只读角色能看不能导，按钮保留但禁用并说明原因。 */
const canExport = computed(() => auth.canExport('policy.crawler_monitoring'))
const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const items = ref<CrawlerTaskItem[]>([])
const total = ref(0)
const exporting = ref(false)
const exportingAbnormal = ref(false)

const overview = ref<CrawlerOverview | null>(null)
const overviewLoading = ref(false)
const overviewError = ref('')
const trendDays = ref(30)

const overviewExpanded = ref(true)
const syncNotice = computed(() => {
  if (!overview.value) return ''
  const { last_sync: sync, data_status: data } = overview.value
  if (sync?.status === 'failed') return '最近一次同步失败，统计可能尚未完整更新。请检查同步日志后重试。'
  if (sync?.status === 'running') return '数据正在同步，统计更新尚未完成。'
  if (data.pending_backfill.days) return `有 ${data.pending_backfill.days} 天历史统计需要重新同步，当前统计暂不完整。`
  if (data.stale) return '统计已超过 36 小时未更新，请检查同步任务。'
  if (!sync) return '尚未同步采集数据。完成首次同步后，这里将显示采集概况。'
  return ''
})

const query = reactive({
  province_name: [] as string[],
  city_name: [] as string[],
  site_name: [] as string[],
  tag: [] as string[],
  health_status: [] as string[],
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/policy/crawler-monitoring/tasks')
const healthLabels = Object.fromEntries(Object.keys(STATUS_BY_LABEL).map(label => [label, label]))
const listQuery = useListQuery(query, load)

const tableColumns = [
  { prop: 'site_name', label: '网站名称', minWidth: 220, grow: 2 },
  { prop: 'tag', label: '标签', minWidth: 240, grow: 2 },
  { prop: 'health_status_label', label: '健康状态', width: 110 },
  { prop: 'stale_days', label: '停更天数', width: 100 },
  { prop: 'last_collect_date', label: '最后采集', fullLabel: '最后采集日期', width: 120 },
  { prop: 'province_name', label: '省份', width: 100 },
  { prop: 'city_name', label: '地市', width: 110 },
  { prop: 'count_7d', label: '近7天', fullLabel: '近7天采集条数', width: 90 },
  { prop: 'count_30d', label: '近30天', fullLabel: '近30天采集条数', width: 100 },
  { prop: 'count_90d', label: '近90天', fullLabel: '近90天采集条数', width: 100 },
  { prop: 'count_total', label: '累计', fullLabel: '统计窗口内累计条数', width: 100 },
  { prop: 'site_code', label: '网站编码', width: 130 },
  { prop: 'in_rules_label', label: '规则在配', fullLabel: '爬虫规则表是否仍有配置', width: 100 },
  { prop: 'source_url', label: '栏目源链接', minWidth: 240, link: true },
] as const

const detailColumns = computed(() => [...tableColumns])
const defaultColumns = tableColumns.map((column) => column.prop)
const selectedColumns = ref<string[]>([...defaultColumns])

let loadSequence = 0

async function load() {
  void listQuery.commit()
  listQuery.captureApplied()
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  const filtered = Object.entries(query).some(
    ([key, value]) => !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
  try {
    const page = await listCrawlerTasks({ ...crawlerFilters(query), page: query.page, page_size: query.page_size })
    if (sequence !== loadSequence) return
    items.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    const message = errorMessage(error, '暂时无法获取任务，请稍后重新加载。')
    loadError.value = message === '请求失败' ? '暂时无法获取任务，请稍后重新加载。' : message
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
    const result = await getCrawlerOverview(trendDays.value)
    if (sequence === overviewSequence) overview.value = result
  } catch (error) {
    if (sequence === overviewSequence) {
      const message = errorMessage(error, '暂时无法获取采集概况，请稍后重试。')
      overviewError.value = message === '请求失败' ? '暂时无法获取采集概况，请稍后重试。' : message
    }
  } finally {
    if (sequence === overviewSequence) overviewLoading.value = false
  }
}

function onSearch() {
  query.page = 1
  void load()
}

function onResetFilters() {
  query.province_name = []
  query.city_name = []
  query.site_name = []
  query.tag = []
  query.health_status = []
  onSearch()
}

/** 点图例把该状态加入多选，再次点击移出。以已生效条件为准，未提交的草稿不参与。 */
function pickStatus(status: HealthStatus) {
  const label = Object.entries(STATUS_BY_LABEL).find(([, value]) => value === status)?.[0] ?? ''
  query.health_status = toggleValue(listQuery.applied.health_status, label)
  onSearch()
}

async function onExport() {
  exporting.value = true
  try {
    await downloadFile(
      '/policy/crawler-monitoring/tasks/export',
      '爬虫监测.xlsx',
      filtersForExport(crawlerFilters(listQuery.applied)),
    )
    ElMessage.success('下载已开始，请查看浏览器下载列表')
  } catch (error) {
    ElMessage.error(errorMessage(error, '导出失败'))
  } finally {
    exporting.value = false
  }
}

async function onExportAbnormal() {
  exportingAbnormal.value = true
  try {
    await downloadFile('/policy/crawler-monitoring/tasks/export', '爬虫异常清单.xlsx', { ...filtersForExport(crawlerFilters(listQuery.applied)), abnormal_only: 'true' })
    ElMessage.success('下载已开始，请查看浏览器下载列表')
  } catch (error) {
    ElMessage.error(errorMessage(error, '导出失败'))
  } finally {
    exportingAbnormal.value = false
  }
}

async function onTrendDays(days: number) {
  trendDays.value = days
  await loadOverview()
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
      hint="按网站与标签查看采集情况，定位停更栏目与异常任务。"
      :loading="loading"
      :error="loadError"
      :total="total"
      @retry="reloadData"
      @change="load"
    >
      <template #actions>
        <el-tooltip
          :content="canExport ? '按当前已生效的筛选条件导出；未筛选时导出全部任务。' : NO_EXPORT_HINT"
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
        <el-tooltip
          :content="canExport ? '在当前已生效筛选结果中，导出断爬和从未出数的任务。' : NO_EXPORT_HINT"
          placement="bottom"
        >
          <span>
            <el-button
              type="danger"
              plain
              :icon="Warning"
              :loading="exportingAbnormal"
              :disabled="!canExport || loading || !!loadError || total === 0"
              @click="onExportAbnormal"
            >
              下载异常清单
            </el-button>
          </span>
        </el-tooltip>
      </template>

      <template #summary>
        <div class="overview-heading">
          <div class="overview-caption">
            <h2>采集概况</h2>
            <span
              v-if="overview?.data_status.last_success_at"
              class="sync-time"
            >更新于 {{ overview.data_status.last_success_at }}</span>
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
              aria-controls="crawler-overview"
              @click="overviewExpanded = !overviewExpanded"
            >
              {{ overviewExpanded ? '收起概览' : '展开概览' }}
            </el-button>
          </div>
        </div>
        <el-alert
          v-if="syncNotice"
          :title="syncNotice"
          :type="overview?.last_sync?.status === 'failed' ? 'error' : 'warning'"
          :closable="false"
          show-icon
          class="sync-notice"
        />
        <section
          v-show="overviewExpanded"
          id="crawler-overview"
          v-loading="overviewLoading"
          class="overview"
        >
          <el-alert
            v-if="overviewError"
            type="error"
            :closable="false"
            show-icon
            :title="overviewError"
          >
            <el-button
              link
              type="primary"
              @click="reloadData"
            >
              重试
            </el-button>
          </el-alert>
          <template v-else-if="overview">
            <div class="cards">
              <div class="card">
                <span class="card-label">昨日采集</span>
                <strong class="card-value">{{ overview.cards.yesterday_rows.toLocaleString() }}</strong>
                <span
                  class="card-foot"
                  :class="{
                    up: overview.cards.yesterday_rows_delta > 0,
                    down: overview.cards.yesterday_rows_delta < 0,
                  }"
                >
                  较前日
                  {{ overview.cards.yesterday_rows_delta >= 0 ? '+' : '' }}{{
                    overview.cards.yesterday_rows_delta.toLocaleString()
                  }}
                </span>
              </div>
              <div class="card">
                <span class="card-label">昨日出数网站</span>
                <strong class="card-value">{{ overview.cards.yesterday_sites.toLocaleString() }}</strong>
                <span class="card-foot">共 {{ overview.cards.sites_total.toLocaleString() }} 个网站</span>
              </div>
              <div class="card card-alert">
                <span class="card-label">异常任务</span>
                <strong class="card-value">{{ overview.cards.abnormal_tasks.toLocaleString() }}</strong>
                <span class="card-foot">断爬与从未出数 / 共 {{ overview.cards.total_tasks.toLocaleString() }} 项</span>
              </div>
              <div class="card card-alert">
                <span class="card-label">整站失联</span>
                <strong class="card-value">{{ overview.cards.sites_all_broken.toLocaleString() }}</strong>
                <span class="card-foot">另有 {{ overview.cards.sites_partial_broken.toLocaleString() }} 个站部分栏目断爬</span>
              </div>
              <div class="card">
                <span class="card-label">健康占比</span>
                <strong class="card-value">{{ overview.cards.healthy_ratio }}%</strong>
                <span class="card-foot">
                  正常与观察任务占比
                </span>
              </div>
            </div>

            <div class="panels">
              <div class="panel">
                <header class="panel-head">
                  <h3>日采集量趋势</h3>
                  <el-radio-group
                    :model-value="trendDays"
                    size="small"
                    @change="(value: string | number | boolean) => onTrendDays(Number(value))"
                  >
                    <el-radio-button :value="30">
                      近30天
                    </el-radio-button>
                    <el-radio-button :value="90">
                      近90天
                    </el-radio-button>
                  </el-radio-group>
                </header>
                <TrendChart :points="overview.trend" />
              </div>
              <div class="panel">
                <header class="panel-head">
                  <h3>任务健康状态</h3>
                  <span class="panel-hint">点击可筛选</span>
                </header>
                <HealthBar
                  :items="overview.health_distribution"
                  :selected="statusValues(listQuery.applied.health_status)"
                  @pick="pickStatus"
                />
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
          <el-form-item label="健康状态">
            <FilterSelect
              v-model="query.health_status"
              v-bind="filters.bind('health_status')"
              :labels="healthLabels"
              size="short"
            />
          </el-form-item>
          <el-form-item label="标签">
            <FilterSelect
              v-model="query.tag"
              v-bind="filters.bind('tag')"
            />
          </el-form-item>
        </FilterBar>
      </template>

      <template #tools>
        <ColumnPicker
          v-model="selectedColumns"
          :columns="detailColumns"
          :defaults="defaultColumns"
        />
      </template>

      <BusinessTable
        :items="items"
        :columns="detailColumns"
        :selected="selectedColumns"
        :summary-keys="['tag', 'health_status_label', 'stale_days']"
        title-key="site_name"
        detail-title="任务详情"
        :can-write="false"
        :loading="loading"
        :filtered="resultFiltered"
        @reset="onResetFilters"
      >
        <template #detail-extra="{ row }">
          <TaskTrend
            :site-key="row.site_key"
            :tag="row.tag"
          />
        </template>
      </BusinessTable>
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
.overview {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-4);
  margin-bottom: var(--zt-space-4);
}

.cards {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--zt-space-3);
}

.card {
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  padding: var(--zt-space-3) var(--zt-space-4);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 110px;
}

.card-label {
  color: var(--zt-ink-500);
  font-size: 13px;
}

.card-value {
  font-size: 28px;
  line-height: 1.2;
  color: var(--zt-ink-900);
  font-variant-numeric: tabular-nums;
}

.card-alert .card-value {
  color: var(--el-color-danger);
}

.card-foot {
  color: var(--zt-ink-500);
  font-size: 12px;
}

.card-foot.up {
  color: #3f8f5e;
}

.card-foot.down {
  color: #c45656;
}

.panels {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) minmax(280px, 1fr);
  gap: var(--zt-space-3);
}

.panel {
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  padding: var(--zt-space-4);
  min-width: 0;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--zt-space-3);
}

.panel-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--zt-ink-900);
}

.panel-hint {
  color: var(--zt-ink-500);
  font-size: 12px;
}

.detail-title {
  margin: var(--zt-space-6) 0 var(--zt-space-3);
  font-size: 14px;
  color: var(--zt-ink-900);
}

.detail-link {
  color: var(--zt-blue-600);
  word-break: break-all;
}

@media (max-width: 1100px) {
  .panels { grid-template-columns: minmax(0, 1fr) minmax(250px, 0.85fr); }
  .cards { gap: 8px; }
}
@media (max-width: 767px) {
  .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .panels { grid-template-columns: minmax(0, 1fr); }
}
</style>
