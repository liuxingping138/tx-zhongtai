<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { importAfterAreaResolve } from '@/api/codebook'
import { clearSources, createSource, importSources, listSources, updateSource, type SourceItem } from '@/api/policy'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import AuditLogButton from '@/components/AuditLogButton.vue'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import ExportButton from '@/components/ExportButton.vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import ImportButton from '@/components/ImportButton.vue'
import ListPage from '@/components/ListPage.vue'
import RecordEditorDrawer from '@/components/RecordEditorDrawer.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useExcelExport } from '@/composables/useExcelExport'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useListLoader } from '@/composables/useListLoader'
import { filtersForExport, useListQuery } from '@/composables/useListQuery'
import { useRecordEditor } from '@/composables/useRecordEditor'
import { useTableSelection } from '@/composables/useTableSelection'
import { useAuthStore } from '@/stores/auth'
import BatchStatusDialog from './BatchStatusDialog.vue'
import { EDITOR_GROUPS, SUMMARY_KEYS, TABLE_COLUMNS, checkArea } from './fields'

const RESOURCE = 'policy.sources'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))
// 上传要先经省市区编码表补地区编码（codebook.area_codes:resolve 是它的查看档）：没这项权限的角色点了只会报「没有权限」，提前说清。
const importBlocked = computed(() =>
  auth.canRead('codebook.area_codes') ? '' : '上传要靠省市区编码表补地区编码，当前角色没有它的查看权限，请找管理员开通',
)
const canPurge = computed(() => auth.canFull(RESOURCE) && auth.isSuperadmin)
const clearing = ref(false)
const selection = useTableSelection<SourceItem>()
const checked = selection.checked
const batchOpen = ref(false)

const query = reactive({
  site_name: [] as string[],
  province_name: [] as string[],
  city_name: [] as string[],
  tag: [] as string[],
  crawl_priority: [] as string[],
  site_type: [] as string[],
  crawler_status: [] as string[],
  site_code: [] as string[],
  online_date_from: '',
  online_date_to: '',
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/policy/sources')
const cityBinding = computed(() => filters.bindCity('city_name', query.province_name))
/** 上线时间区间拆成起止两个参数提交，地址栏和导出都按这两个字段走。 */
const onlineRange = computed<[string, string] | null>({
  get: (): [string, string] | null =>
    query.online_date_from || query.online_date_to ? [query.online_date_from, query.online_date_to] : null,
  set: (value: [string, string] | null) => {
    query.online_date_from = value?.[0] ?? ''
    query.online_date_to = value?.[1] ?? ''
  },
})
const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: listSources,
  errorText: '加载信源失败',
})
const { columns, defaults, selected } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

async function refresh() {
  await Promise.all([load(), filters.load()])
}

async function afterBatch() {
  selection.clear()
  await refresh()
}

const editor = useRecordEditor<SourceItem>({
  noun: '信源',
  groups: EDITOR_GROUPS,
  create: createSource,
  update: (row, form) => updateSource(row.id, { ...form, version: row.version }),
  check: checkArea,
  refresh,
})

async function onImport(file: File) {
  try {
    const result = await runExcelImport(file, (onProgress) =>
      importAfterAreaResolve(file, importSources, onProgress),
    )
    reportImportResult(result, '信源管理-上传校验.xlsx')
    if (!result.rejected) await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

const { exporting, onExport } = useExcelExport({
  path: '/policy/sources/export',
  filename: '信源管理.xlsx',
  filters: () => filtersForExport(listQuery.applied),
})

async function onClear() {
  try {
    await ElMessageBox.confirm(
      '将删除信源管理中的全部数据，且无法恢复。确定清空？',
      '清空信源表',
      {
        type: 'warning',
        confirmButtonText: '确认清空',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  clearing.value = true
  try {
    const result = await clearSources()
    ElMessage.success(`已清空 ${result.deleted} 条`)
    query.page = 1
    await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '清空失败'))
  } finally {
    clearing.value = false
  }
}

onMounted(() => {
  void load()
  void filters.load()
})
</script>

<template>
  <div>
    <ListPage
      title="信源管理"
      hint="维护政策采集网站、所属地区与采集规则。"
      :total="total"
      :page="query.page"
      :page-size="query.page_size"
      :loading="loading"
      :error="loadError"
      @retry="load"
      @update:page="query.page = $event"
      @update:page-size="query.page_size = $event"
      @change="load"
    >
      <template #actions>
        <el-button
          v-if="canWrite"
          type="primary"
          :icon="Plus"
          @click="editor.openCreate"
        >
          新增
        </el-button>
        <ImportButton
          v-if="canWrite"
          hint="上传后自动补齐地区编码；存在重复或地区编码缺失时整批退回，并下载校验报告。"
          :upload="onImport"
          :blocked="importBlocked"
        />
        <ExportButton
          :allowed="auth.canExport(RESOURCE)"
          :loading="exporting"
          @click="onExport"
        />
        <el-button
          v-if="canWrite"
          :disabled="!checked.length"
          @click="batchOpen = true"
        >
          批量改爬虫状态{{ checked.length ? `（${checked.length}）` : '' }}
        </el-button>
        <el-button
          v-if="canPurge"
          type="danger"
          plain
          :loading="clearing"
          @click="onClear"
        >
          清空表
        </el-button>
        <AuditLogButton :module="RESOURCE" />
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
              v-bind="cityBinding"
              size="short"
            />
          </el-form-item>
          <template #advanced>
            <el-form-item label="网站类型">
              <FilterSelect
                v-model="query.site_type"
                v-bind="filters.bind('site_type')"
              />
            </el-form-item>
            <el-form-item label="爬虫状态">
              <FilterSelect
                v-model="query.crawler_status"
                v-bind="filters.bind('crawler_status')"
                size="short"
              />
            </el-form-item>
            <el-form-item label="网站编码">
              <FilterSelect
                v-model="query.site_code"
                v-bind="filters.bind('site_code')"
              />
            </el-form-item>
            <el-form-item
              label="上线时间"
              class="filter-form__item--wide"
            >
              <el-date-picker
                v-model="onlineRange"
                type="daterange"
                value-format="YYYY-MM-DD"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                unlink-panels
              />
            </el-form-item>
            <el-form-item label="标签">
              <FilterSelect
                v-model="query.tag"
                v-bind="filters.bind('tag')"
              />
            </el-form-item>
            <el-form-item label="网站优先级">
              <FilterSelect
                v-model="query.crawl_priority"
                v-bind="filters.bind('crawl_priority')"
              />
            </el-form-item>
          </template>
        </FilterBar>
      </template>
      <template #tools>
        <ColumnPicker
          v-model="selected"
          :columns="columns"
          :defaults="defaults"
          :legacy-defaults="SUMMARY_KEYS"
        />
      </template>
      <BusinessTable
        :ref="selection.bindTable"
        :items="items"
        :selectable="canWrite"
        :columns="columns"
        :groups="EDITOR_GROUPS"
        :selected="selected"
        :summary-keys="SUMMARY_KEYS"
        title-key="site_name"
        detail-title="信源详情"
        :can-write="canWrite"
        :loading="loading"
        :filtered="resultFiltered"
        @reset="listQuery.resetFilters"
        @edit="editor.openEdit"
        @selection-change="checked = $event"
      />
    </ListPage>
    <BatchStatusDialog
      v-model="batchOpen"
      :ids="checked.map(item => item.id)"
      @done="afterBatch"
    />
    <RecordEditorDrawer
      :editor="editor"
      :groups="EDITOR_GROUPS"
    />
  </div>
</template>

