<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  CRAWLER_V2_BASE,
  listCrawlerSites,
  type CrawlerSiteItem,
  type CrawlerSiteRef,
  type SiteStatus,
} from '@/api/crawlerMonitoringV2'
import { errorMessage } from '@/api/errors'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import ExportButton from '@/components/ExportButton.vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import ListPage from '@/components/ListPage.vue'
import { useExcelExport } from '@/composables/useExcelExport'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useAuthStore } from '@/stores/auth'
import { filtersForExport, toggleValue, useListQuery } from '@/composables/useListQuery'
import CrawlerOverview from './CrawlerOverview.vue'
import CrawlerSiteTrend from './CrawlerSiteTrend.vue'
import { siteFilters, STATUS_BY_LABEL, statusValues } from './filters'

const LIST_ERROR = '暂时无法获取网站列表，请稍后重新加载。'
const auth = useAuthStore()

const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const items = ref<CrawlerSiteItem[]>([])
const total = ref(0)

const overviewPanel = ref<InstanceType<typeof CrawlerOverview>>()

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
const { exporting, onExport } = useExcelExport({
  path: `${CRAWLER_V2_BASE}/sites/export`,
  filename: '爬虫监测.xlsx',
  filters: () => filtersForExport(siteFilters(listQuery.applied)),
})

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

/** 点卡片把该状态加入多选，再次点击移出。以已生效条件为准，未提交的草稿不参与。 */
function pickStatus(status: SiteStatus) {
  const label = Object.entries(STATUS_BY_LABEL).find(([, value]) => value === status)?.[0] ?? ''
  listQuery.replaceApplied('status', toggleValue(listQuery.applied.status, label))
  void load()
}

/** 点省份条形：按该省份所有原始写法筛选，再点同一省份取消。 */
function pickProvince(rawNames: string[]) {
  const current = [...listQuery.applied.province_name].sort().join('|')
  listQuery.replaceApplied('province_name', current === [...rawNames].sort().join('|') ? [] : rawNames)
  void load()
}

/** 需关注清单里点「在下方列表中查看」：按该网站的原始名称、省份、地市精确定位。 */
function locateSite(site: CrawlerSiteRef) {
  listQuery.replaceApplied('site_name', [site.site_name])
  listQuery.replaceApplied('province_name', site.province_name ? [site.province_name] : [])
  listQuery.replaceApplied('city_name', site.city_name ? [site.city_name] : [])
  listQuery.replaceApplied('status', [])
  void load()
}

async function reloadData() {
  await Promise.all([load(), overviewPanel.value?.reload(), filters.load()])
}

onMounted(() => { void reloadData() })
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
        <ExportButton
          :allowed="auth.canExport('policy.crawler_monitoring_v2')"
          :loading="exporting"
          :disabled="loading || !!loadError || total === 0"
          hint="按当前已生效的筛选条件导出网站明细。"
          @click="onExport"
        />
      </template>

      <template #summary>
        <CrawlerOverview
          ref="overviewPanel"
          :selected-statuses="appliedStatuses"
          @pick-status="pickStatus"
          @pick-province="pickProvince"
          @locate-site="locateSite"
          @retry="reloadData"
        />
      </template>

      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          @search="listQuery.search"
          @reset="listQuery.resetFilters"
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
        @reset="listQuery.resetFilters"
      >
        <template #detail-extra="{ row }">
          <CrawlerSiteTrend :site="row" />
        </template>
      </BusinessTable>
    </ListPage>
  </div>
</template>
