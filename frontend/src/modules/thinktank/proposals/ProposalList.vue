<script setup lang="ts">
import { Download, StarFilled, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

import { downloadBlob } from '@/api/download'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import {
  deleteProposal,
  downloadProposalBlob,
  exportUndefinedProposals,
  favoriteProposal,
  listProposalLogs,
  listProposals,
  unfavoriteProposal,
  uploadProposalTags,
  type ProposalItem,
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
import ProposalUploadDialog from './ProposalUploadDialog.vue'
import {
  PROPOSAL_EDITOR_GROUPS,
  PROPOSAL_FILTER_DEFS,
  PROPOSAL_SUMMARY_KEYS,
  PROPOSAL_TABLE_COLUMNS,
  type ProposalDynamicOptions,
} from './fields'

const RESOURCE = 'thinktank.proposals'
const ACTION_WIDTH = 132
const auth = useAuthStore()
const canManage = computed(() => auth.canFull(RESOURCE))
const canExport = computed(() => auth.canExport(RESOURCE))

const query = reactive({
  proposal_name: [] as string[], customer_name: [] as string[], proposal_type: [] as string[],
  industry_tags: [] as string[], region_tag: [] as string[], opportunity_source: [] as string[],
  bidding_method: [] as string[], bid_deadline: [] as string[], owner_dept: [] as string[],
  owner_name: [] as string[], result_status: [] as string[], tag_status: [] as string[],
  favorite_only: [] as string[], page: 1, page_size: 20,
})

const filters = useFilterOptions('/thinktank/proposals')
const dynamicOptions = computed<ProposalDynamicOptions>(() => ({
  proposal_type: filters.get('proposal_type').items,
  industry_tags: filters.get('industry_tags').items,
  region_tag: filters.get('region_tag').items,
  opportunity_source: filters.get('opportunity_source').items,
  bidding_method: filters.get('bidding_method').items,
  owner_dept: filters.get('owner_dept').items,
  result_status: filters.get('result_status').items,
}))

const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: listProposals,
  errorText: '加载方案库列表失败',
})
const { columns, defaults, selected } = useDetailColumns(PROPOSAL_TABLE_COLUMNS, PROPOSAL_EDITOR_GROUPS)

const uploadVisible = ref(false)
const exportingUndefined = ref(false)
const busyRowIds = reactive(new Set<string>())
const downloadingRowIds = reactive(new Set<string>())
const logTarget = ref<{ visible: boolean; id: string; name: string }>({ visible: false, id: '', name: '' })
const selection = useTableSelection<ProposalItem>()
const checked = selection.checked

async function refresh() {
  await Promise.all([load(), filters.load()])
}

const batch = useThinktankBatch({
  checked,
  clearSelection: selection.clear,
  refresh,
  itemNoun: '方案',
  api: {
    favorite: favoriteProposal,
    unfavorite: unfavoriteProposal,
    remove: deleteProposal,
    download: downloadProposalBlob,
    getTitle: row => row.proposal_name,
  },
})

function detailRoute(row: ProposalItem, index: number): RouteLocationRaw {
  const position = (query.page - 1) * query.page_size + index
  return {
    path: `/thinktank/proposals/${encodeURIComponent(row.id)}`,
    query: reviewQuery(listQuery.applied, position, query.page_size),
  }
}

function editRoute(row: ProposalItem, index: number): RouteLocationRaw {
  const to = detailRoute(row, index)
  return typeof to === 'string' ? { path: to, query: { edit: '1' } } : { ...to, query: { ...to.query, edit: '1' } }
}

const { exporting, onExport } = useExcelExport({
  path: '/thinktank/proposals/export',
  filename: '方案库.xlsx',
  filters: () => filtersForExport(listQuery.applied),
})

async function onExportUndefined() {
  if (exportingUndefined.value) return
  exportingUndefined.value = true
  try {
    const resp = await exportUndefinedProposals()
    const filename = parseContentDispositionFilename(resp.headers?.['content-disposition'], '方案库未定义数据.xlsx')
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
    const result = await runExcelImport(file, onProgress => uploadProposalTags(file, onProgress))
    reportImportResult(result, '方案库标签导入结果.xlsx')
    await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '上传方案标签失败'))
  }
  return false
}

async function onToggleFavorite(row: ProposalItem) {
  if (busyRowIds.has(row.id)) return
  busyRowIds.add(row.id)
  try {
    const res = row.is_favorited ? await unfavoriteProposal(row.id) : await favoriteProposal(row.id)
    row.is_favorited = res.is_favorited
    ElMessage.success(res.is_favorited ? '收藏成功' : '已取消收藏')
  } catch (error) {
    ElMessage.error(errorMessage(error, '收藏操作失败'))
  } finally {
    busyRowIds.delete(row.id)
  }
}

async function onDownload(row: ProposalItem) {
  if (downloadingRowIds.has(row.id)) return
  downloadingRowIds.add(row.id)
  const hint = ElMessage.info({ message: `正在下载「${row.proposal_name}」，请稍候…`, duration: 0 })
  try {
    const resp = await downloadProposalBlob(row.id)
    const filename = parseContentDispositionFilename(resp.headers?.['content-disposition'], row.proposal_name)
    downloadBlob(resp.data, filename)
    ElMessage.success('文件下载已开始')
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败'))
  } finally {
    hint.close()
    downloadingRowIds.delete(row.id)
  }
}

function onOpenLogs(row: ProposalItem) {
  logTarget.value = { visible: true, id: row.id, name: row.proposal_name }
}

async function onDeleteRow(row: ProposalItem) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.proposal_name}」吗？删除后将记入操作审计。`, '删除确认', { type: 'warning' })
    await deleteProposal(row.id)
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
      title="方案库"
      hint="沉淀招投标与行业解决方案，追踪报价与中标结果，支持在线预览、收藏、下载与标签治理。"
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
            hint="上传导出的未定义标签 Excel 模板，批量完善方案标签并记录操作审计。"
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
          <AuditLogButton module="thinktank.proposals" />
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
            :defs="PROPOSAL_FILTER_DEFS"
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
        title-key="proposal_name"
        :summary-keys="PROPOSAL_SUMMARY_KEYS"
        :groups="PROPOSAL_EDITOR_GROUPS"
        :detail-route="detailRoute"
        :can-write="canManage"
        :action-width="ACTION_WIDTH"
        :loading="loading"
        :filtered="resultFiltered"
        detail-title="方案详情"
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

        <template #cell-proposal_type="{ row }">
          <el-tag
            size="small"
            :type="row.proposal_type ? 'primary' : 'warning'"
          >
            {{ displayCategory(row.proposal_type) }}
          </el-tag>
        </template>

        <template #row-actions="{ row, index }">
          <ThinktankRowActions
            v-if="row?.id"
            :title="row.proposal_name"
            :can-edit="row.can_edit"
            :can-export="row.can_export"
            :is-favorited="row.is_favorited"
            :detail-to="detailRoute(row, index)"
            :edit-to="editRoute(row, index)"
            :busy="busyRowIds.has(row.id)"
            :downloading="downloadingRowIds.has(row.id)"
            item-noun="方案"
            @download="onDownload(row)"
            @favorite="onToggleFavorite(row)"
            @logs="onOpenLogs(row)"
            @delete="onDeleteRow(row)"
          />
        </template>
      </BusinessTable>
    </ListPage>

    <ProposalUploadDialog
      v-model="uploadVisible"
      :options="dynamicOptions"
      @uploaded="refresh"
    />
    <ThinktankLogsDrawer
      v-model="logTarget.visible"
      :file-id="logTarget.id"
      :file-name="logTarget.name"
      :fetch-logs="listProposalLogs"
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
