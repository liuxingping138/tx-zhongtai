<script setup lang="ts">
import { Download, StarFilled, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

import { downloadBlob } from '@/api/download'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import {
  deleteReport,
  downloadReportBlob,
  exportUndefinedReports,
  favoriteReport,
  listReportLogs,
  listReports,
  unfavoriteReport,
  uploadReportTags,
  type ReportItem,
} from '@/api/thinktank'
import AuditLogButton from '@/components/AuditLogButton.vue'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import ExportButton from '@/components/ExportButton.vue'
import FilterBar from '@/components/FilterBar.vue'
import ImportButton from '@/components/ImportButton.vue'
import ListPage from '@/components/ListPage.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useExcelExport } from '@/composables/useExcelExport'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useListLoader } from '@/composables/useListLoader'
import { filtersForExport, useListQuery } from '@/composables/useListQuery'
import { useTableSelection } from '@/composables/useTableSelection'
import { reviewQuery } from '@/modules/policy/shared/reviewQuery'
import { useAuthStore } from '@/stores/auth'
import { displayCategory, parseContentDispositionFilename } from '../shared/options'
import ThinktankBatchToolbar from '../shared/ThinktankBatchToolbar.vue'
import ThinktankFilterGrid from '../shared/ThinktankFilterGrid.vue'
import ThinktankLogsDrawer from '../shared/ThinktankLogsDrawer.vue'
import ThinktankRowActions from '../shared/ThinktankRowActions.vue'
import { useThinktankBatch } from '../shared/useThinktankBatch'
import ReportUploadDialog from './ReportUploadDialog.vue'
import {
  REPORT_EDITOR_GROUPS,
  REPORT_FILTER_DEFS,
  REPORT_SUMMARY_KEYS,
  REPORT_TABLE_COLUMNS,
  type ReportDynamicOptions,
} from './fields'

const RESOURCE = 'thinktank.reports'
const ACTION_WIDTH = 132
const auth = useAuthStore()
const canManage = computed(() => auth.canFull(RESOURCE))
const canExport = computed(() => auth.canExport(RESOURCE))

const query = reactive({
  report_name: [] as string[], project_name: [] as string[], customer_name: [] as string[],
  report_type: [] as string[], industry_tags: [] as string[], region_tag: [] as string[],
  delivery_dept: [] as string[], participants: [] as string[], is_temp_support: [] as string[],
  delivery_date: [] as string[], keywords: [] as string[], tag_status: [] as string[],
  favorite_only: [] as string[], page: 1, page_size: 20,
})

const filters = useFilterOptions('/thinktank/reports')
const dynamicOptions = computed<ReportDynamicOptions>(() => ({
  report_type: filters.get('report_type').items,
  industry_tags: filters.get('industry_tags').items,
  region_tag: filters.get('region_tag').items,
  delivery_dept: filters.get('delivery_dept').items,
  is_temp_support: filters.get('is_temp_support').items,
}))

const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: listReports,
  errorText: '加载报告库列表失败',
})
const { columns, defaults, selected } = useDetailColumns(REPORT_TABLE_COLUMNS, REPORT_EDITOR_GROUPS)

const uploadVisible = ref(false)
const exportingUndefined = ref(false)
const busyRowIds = reactive(new Set<string>())
const downloadingRowIds = reactive(new Set<string>())
const logTarget = ref<{ visible: boolean; id: string; name: string }>({ visible: false, id: '', name: '' })
const selection = useTableSelection<ReportItem>()
const checked = selection.checked

async function refresh() {
  await Promise.all([load(), filters.load()])
}

const batch = useThinktankBatch({
  checked,
  clearSelection: selection.clear,
  refresh,
  itemNoun: '报告',
  api: {
    favorite: favoriteReport,
    unfavorite: unfavoriteReport,
    remove: deleteReport,
    download: downloadReportBlob,
    getTitle: row => row.report_name,
  },
})

function detailRoute(row: ReportItem, index: number): RouteLocationRaw {
  const position = (query.page - 1) * query.page_size + index
  return {
    path: `/thinktank/reports/${encodeURIComponent(row.id)}`,
    query: reviewQuery(listQuery.applied, position, query.page_size),
  }
}

function editRoute(row: ReportItem, index: number): RouteLocationRaw {
  const to = detailRoute(row, index)
  return typeof to === 'string' ? { path: to, query: { edit: '1' } } : { ...to, query: { ...to.query, edit: '1' } }
}

const { exporting, onExport } = useExcelExport({
  path: '/thinktank/reports/export',
  filename: '报告库.xlsx',
  filters: () => filtersForExport(listQuery.applied),
})

async function onExportUndefined() {
  if (exportingUndefined.value) return
  exportingUndefined.value = true
  try {
    const resp = await exportUndefinedReports()
    const filename = parseContentDispositionFilename(resp.headers?.['content-disposition'], '报告库未定义数据.xlsx')
    downloadBlob(resp.data, filename)
    ElMessage.success('未定义数据下载已开始')
  } catch (error) {
    ElMessage.error(errorMessage(error, '导出未定义数据失败'))
  } finally {
    exportingUndefined.value = false
  }
}

async function onUploadTags(file: File) {
  try {
    const result = await runExcelImport(file, onProgress => uploadReportTags(file, onProgress))
    reportImportResult(result, '报告库标签导入结果.xlsx')
    await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '上传报告标签失败'))
  }
  return false
}

async function onToggleFavorite(row: ReportItem) {
  if (busyRowIds.has(row.id)) return
  busyRowIds.add(row.id)
  try {
    const res = row.is_favorited ? await unfavoriteReport(row.id) : await favoriteReport(row.id)
    row.is_favorited = res.is_favorited
    ElMessage.success(res.is_favorited ? '收藏成功' : '已取消收藏')
  } catch (error) {
    ElMessage.error(errorMessage(error, '收藏操作失败'))
  } finally {
    busyRowIds.delete(row.id)
  }
}

async function onDownload(row: ReportItem) {
  if (downloadingRowIds.has(row.id)) return
  downloadingRowIds.add(row.id)
  const hint = ElMessage.info({ message: `正在下载「${row.report_name}」，请稍候…`, duration: 0 })
  try {
    const resp = await downloadReportBlob(row.id)
    const filename = parseContentDispositionFilename(resp.headers?.['content-disposition'], row.report_name)
    downloadBlob(resp.data, filename)
    ElMessage.success('文件下载已开始')
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败'))
  } finally {
    hint.close()
    downloadingRowIds.delete(row.id)
  }
}

function onOpenLogs(row: ReportItem) {
  logTarget.value = { visible: true, id: row.id, name: row.report_name }
}

async function onDeleteRow(row: ReportItem) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.report_name}」吗？删除后将记入操作审计。`, '删除确认', { type: 'warning' })
    await deleteReport(row.id)
    ElMessage.success('删除成功')
    await refresh()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorMessage(error, '删除失败'))
  }
}

function onFilterUpdate(field: string, val: string[]) {
  if (field in query) (query as unknown as Record<string, string[]>)[field] = val
}

onMounted(() => { void Promise.all([load(), filters.load()]) })
</script>

<template>
  <div>
    <ListPage
      title="报告库"
      hint="沉淀行业研究、客户专项与项目交付报告，支持在线预览、收藏、下载与批量标签治理。"
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
      <template #total>
        <template v-if="checked.length">
          已选 <strong>{{ checked.length }}</strong> 项
          <button
            type="button"
            class="selection-clear"
            @click="selection.clear"
          >
            取消选择
          </button>
        </template>
        <template v-else>
          共 <strong>{{ total.toLocaleString('zh-CN') }}</strong> 条记录
        </template>
      </template>

      <template #actions>
        <template v-if="!checked.length">
          <el-button
            v-if="canManage"
            type="primary"
            :icon="Upload"
            @click="uploadVisible = true"
          >
            上传文件
          </el-button>
          <ImportButton
            v-if="canManage"
            label="上传标签"
            hint="上传导出的未定义标签 Excel 模板，批量完善报告标签并记录操作审计。"
            :upload="onUploadTags"
          />
          <el-button
            v-if="canExport"
            :icon="Download"
            :loading="exportingUndefined"
            @click="onExportUndefined"
          >
            导出未定义数据
          </el-button>
          <ExportButton
            :allowed="canExport"
            :loading="exporting"
            @click="onExport"
          />
          <AuditLogButton module="thinktank.reports" />
        </template>
        <template v-else>
          <ThinktankBatchToolbar
            :unfavorited-count="batch.unfavorited.value.length"
            :favorited-count="batch.favorited.value.length"
            :downloadable-count="batch.downloadable.value.length"
            :deletable-count="batch.deletable.value.length"
            :can-delete="canManage"
            :busy="batch.batchBusy.value"
            @favorite="batch.onBatchFavorite"
            @unfavorite="batch.onBatchUnfavorite(listQuery.applied.favorite_only.length > 0)"
            @download="batch.onBatchDownload"
            @delete="batch.onBatchDelete"
          />
        </template>
      </template>

      <template #filters>
        <FilterBar
          class="thinktank-filters"
          :query="query"
          :applied="listQuery.applied"
          label-position="left"
          @search="listQuery.search"
          @reset="listQuery.resetFilters"
        >
          <ThinktankFilterGrid
            :defs="REPORT_FILTER_DEFS"
            :query="query as unknown as Record<string, string[]>"
            :filters="filters"
            @update="onFilterUpdate"
          />
        </FilterBar>
      </template>

      <template #tools>
        <ColumnPicker
          v-model="selected"
          :columns="columns"
          :defaults="defaults"
        />
      </template>

      <BusinessTable
        :ref="selection.bindTable"
        :items="items"
        :columns="columns"
        :selected="selected"
        selectable
        title-key="report_name"
        :summary-keys="REPORT_SUMMARY_KEYS"
        :groups="REPORT_EDITOR_GROUPS"
        :detail-route="detailRoute"
        :can-write="canManage"
        :action-width="ACTION_WIDTH"
        :loading="loading"
        :filtered="resultFiltered"
        detail-title="报告详情"
        @reset="listQuery.resetFilters"
        @selection-change="checked = $event"
      >
        <template #title-prefix="{ row }">
          <el-icon
            v-if="row?.is_favorited"
            class="fav-star"
            title="已收藏"
            aria-label="已收藏"
          >
            <StarFilled />
          </el-icon>
        </template>

        <template #cell-report_type="{ row }">
          <el-tag
            size="small"
            :type="row.report_type ? 'primary' : 'warning'"
          >
            {{ displayCategory(row.report_type) }}
          </el-tag>
        </template>

        <template #row-actions="{ row, index }">
          <ThinktankRowActions
            v-if="row?.id"
            :title="row.report_name"
            :can-edit="row.can_edit"
            :can-download="row.can_download"
            :is-favorited="row.is_favorited"
            :detail-to="detailRoute(row, index)"
            :edit-to="editRoute(row, index)"
            :busy="busyRowIds.has(row.id)"
            :downloading="downloadingRowIds.has(row.id)"
            item-noun="报告"
            @download="onDownload(row)"
            @favorite="onToggleFavorite(row)"
            @logs="onOpenLogs(row)"
            @delete="onDeleteRow(row)"
          />
        </template>
      </BusinessTable>
    </ListPage>

    <ReportUploadDialog
      v-model="uploadVisible"
      :options="dynamicOptions"
      @uploaded="refresh"
    />
    <ThinktankLogsDrawer
      v-model="logTarget.visible"
      :file-id="logTarget.id"
      :file-name="logTarget.name"
      :fetch-logs="listReportLogs"
    />
  </div>
</template>

<style scoped>
.fav-star { color: var(--zt-warning); font-size: 14px; flex-shrink: 0; }
.selection-clear { padding: 0 4px; border: 0; background: none; color: var(--zt-blue-600); font: inherit; cursor: pointer; }
.selection-clear:hover { text-decoration: underline; }
.thinktank-filters { align-items: flex-start; }
.thinktank-filters :deep(.filter-bar__fields) { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px 16px; align-items: center; }
.thinktank-filters :deep(.filter-bar__fields > .el-form-item),
.thinktank-filters :deep(.filter-bar__fields > .el-form-item:first-child) { max-width: none; width: 100%; margin: 0; }
.thinktank-filters :deep(.el-form-item__label) { width: 72px; justify-content: flex-end; text-align: right; margin: 0 8px 0 0; }
@media (max-width: 1279px) { .thinktank-filters :deep(.filter-bar__fields) { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 959px) { .thinktank-filters :deep(.filter-bar__fields) { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 767px) { .thinktank-filters :deep(.filter-bar__fields) { grid-template-columns: 1fr; } }
</style>
