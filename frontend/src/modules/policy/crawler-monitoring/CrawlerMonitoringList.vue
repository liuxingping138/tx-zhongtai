<script setup lang="ts">
import { Download, Warning } from '@element-plus/icons-vue'
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
import { filtersForExport, useListQuery } from '@/composables/useListQuery'
import HealthBar from './HealthBar.vue'
import TaskTrend from './TaskTrend.vue'
import TrendChart from './TrendChart.vue'

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

const STATUS_BY_LABEL: Record<string, HealthStatus> = {
  正常: 'normal',
  观察: 'watch',
  断爬: 'broken',
  从未出数: 'never',
}

const query = reactive({
  province_name: '',
  city_name: '',
  site_name: '',
  tag: '',
  health_status: '',
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/policy/crawler-monitoring/tasks')
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

function currentFilters() {
  return {
    province_name: query.province_name || undefined,
    city_name: query.city_name || undefined,
    site_name: query.site_name || undefined,
    tag: query.tag || undefined,
    health_status: STATUS_BY_LABEL[query.health_status] || undefined,
  }
}

let loadSequence = 0

async function load() {
  void listQuery.commit()
  listQuery.captureApplied()
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  const filtered = Object.entries(query).some(
    ([key, value]) => !['page', 'page_size'].includes(key) && Boolean(value),
  )
  try {
    const page = await listCrawlerTasks({ ...currentFilters(), page: query.page, page_size: query.page_size })
    if (sequence !== loadSequence) return
    items.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = errorMessage(error, '加载爬虫监测失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function loadOverview() {
  overviewLoading.value = true
  overviewError.value = ''
  try {
    overview.value = await getCrawlerOverview(trendDays.value)
  } catch (error) {
    overviewError.value = errorMessage(error, '加载概览失败')
  } finally {
    overviewLoading.value = false
  }
}

function onSearch() {
  query.page = 1
  void load()
}

function onResetFilters() {
  query.province_name = ''
  query.city_name = ''
  query.site_name = ''
  query.tag = ''
  query.health_status = ''
  onSearch()
}

function pickStatus(status: HealthStatus) {
  const label = Object.entries(STATUS_BY_LABEL).find(([, value]) => value === status)?.[0] ?? ''
  query.health_status = label
  onSearch()
}

async function onExport() {
  exporting.value = true
  try {
    await downloadFile(
      '/policy/crawler-monitoring/tasks/export',
      '爬虫监测.xlsx',
      filtersForExport(listQuery.applied),
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
    await downloadFile('/policy/crawler-monitoring/tasks/export', '爬虫异常清单.xlsx', { abnormal_only: 'true' })
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

onMounted(() => {
  void load()
  void loadOverview()
  void filters.load()
})
</script>

<template>
  <div>
    <ListPage
      v-model:page="query.page"
      v-model:page-size="query.page_size"
      title="爬虫监测"
      hint="按「网站 + 标签」监测政策爬虫的采集情况。统计每天同步一次，停更天数按最后一次采集到数据的日期计算。"
      :loading="loading"
      :error="loadError"
      :total="total"
      @retry="load"
      @change="load"
    >
      <template #actions>
        <el-tooltip
          content="按当前已生效的筛选条件导出；未筛选时导出全部任务。"
          placement="bottom"
        >
          <el-button
            :icon="Download"
            :loading="exporting"
            @click="onExport"
          >
            下载 Excel
          </el-button>
        </el-tooltip>
        <el-tooltip
          content="只导出断爬和从未出数的任务，用于排查和派单。"
          placement="bottom"
        >
          <el-button
            type="danger"
            plain
            :icon="Warning"
            :loading="exportingAbnormal"
            @click="onExportAbnormal"
          >
            下载异常清单
          </el-button>
        </el-tooltip>
      </template>

      <template #summary>
        <section
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
              @click="loadOverview"
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
                <span class="card-label">断爬任务</span>
                <strong class="card-value">{{ overview.cards.abnormal_tasks.toLocaleString() }}</strong>
                <span class="card-foot">共 {{ overview.cards.total_tasks.toLocaleString() }} 个任务</span>
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
                  {{ overview.last_sync?.finished_at ? `同步于 ${overview.last_sync.finished_at}` : '尚未同步' }}
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
            :site-code="row.site_code"
            :tag="row.tag"
          />
        </template>
      </BusinessTable>
    </ListPage>
  </div>
</template>

<style scoped>
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
  gap: 2px;
}

.card-label {
  color: var(--zt-ink-500);
  font-size: 13px;
}

.card-value {
  font-size: 26px;
  line-height: 1.2;
  color: var(--zt-ink-900);
  font-variant-numeric: tabular-nums;
}

.card-alert .card-value {
  color: #c45656;
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
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: var(--zt-space-3);
}

.panel {
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  padding: var(--zt-space-3) var(--zt-space-4) var(--zt-space-4);
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

@media (max-width: 1280px) {
  .cards {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .panels {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
