<script setup lang="ts">
import { Download, Star, StarFilled, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

import { downloadBlob } from '@/api/download'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import {
  deleteKnowledge,
  downloadKnowledgeBlob,
  exportUndefinedKnowledge,
  favoriteKnowledge,
  getKnowledgeAccess,
  listKnowledge,
  unfavoriteKnowledge,
  uploadKnowledgeTags,
  type KnowledgeAccessSummary,
  type KnowledgeItem,
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
import { reviewQuery } from '@/modules/policy/shared/reviewQuery'
import { useAuthStore } from '@/stores/auth'
import KnowledgeFilters, { type KnowledgeFilterQuery } from './KnowledgeFilters.vue'
import KnowledgeLogsDrawer from './KnowledgeLogsDrawer.vue'
import KnowledgeUploadDialog from './KnowledgeUploadDialog.vue'
import {
  displayFileType,
  EDITOR_GROUPS,
  parseContentDispositionFilename,
  SUMMARY_KEYS,
  TABLE_COLUMNS,
} from './fields'

const RESOURCE = 'thinktank.knowledge'
const auth = useAuthStore()
const canCreate = computed(() => auth.canFull(RESOURCE))
const canExportUndefined = computed(
  () => auth.canExport(RESOURCE) && (accessScope.value?.exportable_file_types.includes('未定义') ?? true),
)
const canUploadTags = computed(() => auth.canFull(RESOURCE))

const query = reactive({
  file_name: [] as string[],
  file_type: [] as string[],
  operator_type: [] as string[],
  product_type: [] as string[],
  product_sub_type: [] as string[],
  industry_type: [] as string[],
  prov_name: [] as string[],
  app_scenario: [] as string[],
  depart_affiliation: [] as string[],
  market_category: [] as string[],
  data_time: [] as string[],
  tag_status: [] as string[],
  favorite_only: [] as string[],
  page: 1,
  page_size: 20,
})

const filters = useFilterOptions('/thinktank/knowledge')
const accessScope = ref<KnowledgeAccessSummary | null>(null)
const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: listKnowledge,
  errorText: '加载知识库列表失败',
})
const { columns, defaults, selected } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

const uploadVisible = ref(false)
const exportingUndefined = ref(false)
const busyRowIds = reactive(new Set<string>())
const logTarget = ref<{ visible: boolean; id: string; name: string }>({ visible: false, id: '', name: '' })

async function refresh() {
  await Promise.all([load(), filters.load()])
}

function detailRoute(row: KnowledgeItem, index: number): RouteLocationRaw {
  const position = (query.page - 1) * query.page_size + index
  return {
    name: 'thinktank-knowledge-preview',
    params: { id: row.id },
    query: reviewQuery(listQuery.applied, position, query.page_size),
  }
}

function editRoute(row: KnowledgeItem, index: number): RouteLocationRaw {
  const to = detailRoute(row, index)
  return typeof to === 'string' ? { path: to, query: { edit: '1' } } : { ...to, query: { ...to.query, edit: '1' } }
}

const { exporting, onExport } = useExcelExport({
  path: '/thinktank/knowledge/export',
  filename: '知识库资料.xlsx',
  filters: () => filtersForExport(listQuery.applied),
})

async function onExportUndefined() {
  if (exportingUndefined.value) return
  exportingUndefined.value = true
  try {
    const resp = await exportUndefinedKnowledge()
    const filename = parseContentDispositionFilename(resp.headers?.['content-disposition'], '未定义标签数据.xlsx')
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
    const result = await runExcelImport(file, onProgress => uploadKnowledgeTags(file, onProgress))
    reportImportResult(result, '知识标签-跳过明细.xlsx')
    await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '上传知识标签失败'))
  }
  return false
}

async function onToggleFavorite(row: KnowledgeItem) {
  if (busyRowIds.has(row.id)) return
  busyRowIds.add(row.id)
  try {
    const res = row.is_favorited ? await unfavoriteKnowledge(row.id) : await favoriteKnowledge(row.id)
    row.is_favorited = res.is_favorited
    ElMessage.success(res.is_favorited ? '收藏成功' : '已取消收藏')
  } catch (error) {
    ElMessage.error(errorMessage(error, '收藏操作失败'))
  } finally {
    busyRowIds.delete(row.id)
  }
}

async function onDownload(row: KnowledgeItem) {
  if (busyRowIds.has(row.id)) return
  busyRowIds.add(row.id)
  try {
    const resp = await downloadKnowledgeBlob(row.id)
    const filename = parseContentDispositionFilename(resp.headers?.['content-disposition'], row.file_name)
    downloadBlob(resp.data, filename)
    ElMessage.success('开始下载文件')
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败'))
  } finally {
    busyRowIds.delete(row.id)
  }
}

function onOpenLogs(row: KnowledgeItem) {
  logTarget.value = { visible: true, id: row.id, name: row.file_name }
}

async function onDeleteRow(row: KnowledgeItem) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.file_name}」吗？删除后将记入操作审计。`, '删除确认', {
      type: 'warning',
    })
    await deleteKnowledge(row.id)
    ElMessage.success('删除成功')
    await refresh()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorMessage(error, '删除失败'))
  }
}

function onFilterUpdate(field: keyof KnowledgeFilterQuery, val: string[]) {
  query[field] = val
}

onMounted(async () => {
  await Promise.all([
    load(),
    filters.load(),
    getKnowledgeAccess().then(res => { accessScope.value = res }).catch(() => {}),
  ])
})
</script>

<template>
  <div>
    <ListPage
      title="智库知识库"
      hint="按文件类型与行业类型授权检索、预览、收藏、下载、标签完善，全操作留痕审计。"
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
          v-if="canCreate"
          type="primary"
          :icon="Upload"
          @click="uploadVisible = true"
        >
          上传文件
        </el-button>
        <ImportButton
          v-if="canUploadTags"
          label="上传知识标签"
          hint="上传导出的未定义标签 Excel 模板，批量完善标签并记录操作审计。"
          :upload="onUploadTags"
        />
        <el-button
          v-if="canExportUndefined"
          :icon="Download"
          :loading="exportingUndefined"
          @click="onExportUndefined"
        >
          导出未定义数据
        </el-button>
        <ExportButton
          :allowed="auth.canExport(RESOURCE)"
          :loading="exporting"
          @click="onExport"
        />
        <AuditLogButton module="thinktank.knowledge" />
      </template>

      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          :collapsible="false"
          @search="listQuery.search"
          @reset="listQuery.resetFilters"
        >
          <KnowledgeFilters
            :query="query"
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
        :items="items"
        :columns="columns"
        :selected="selected"
        title-key="file_name"
        :summary-keys="SUMMARY_KEYS"
        :groups="EDITOR_GROUPS"
        :detail-route="detailRoute"
        :can-write="canCreate"
        :action-width="340"
        :loading="loading"
        :filtered="resultFiltered"
        detail-title="知识资料详情"
        @reset="listQuery.resetFilters"
      >
        <template #cell-file_type="{ row }">
          <el-tag
            size="small"
            :type="row.file_type ? 'primary' : 'warning'"
          >
            {{ displayFileType(row.file_type) }}
          </el-tag>
        </template>

        <template #row-actions="{ row, index }">
          <div class="row-actions">
            <RouterLink
              class="row-action"
              :to="detailRoute(row, index)"
            >
              查看
            </RouterLink>
            <RouterLink
              v-if="row.can_edit"
              class="row-action row-action--primary"
              :to="editRoute(row, index)"
            >
              编辑
            </RouterLink>
            <button
              type="button"
              class="row-action"
              :disabled="busyRowIds.has(row.id)"
              @click="onToggleFavorite(row)"
            >
              <el-icon><StarFilled v-if="row.is_favorited" /><Star v-else /></el-icon>
              {{ row.is_favorited ? '已收藏' : '收藏' }}
            </button>
            <button
              v-if="row.can_export"
              type="button"
              class="row-action"
              :disabled="busyRowIds.has(row.id)"
              @click="onDownload(row)"
            >
              下载
            </button>
            <button
              type="button"
              class="row-action"
              @click="onOpenLogs(row)"
            >
              日志
            </button>
            <button
              v-if="row.can_edit"
              type="button"
              class="row-action row-action--danger"
              @click="onDeleteRow(row)"
            >
              删除
            </button>
          </div>
        </template>
      </BusinessTable>
    </ListPage>

    <KnowledgeUploadDialog
      v-model="uploadVisible"
      :provinces="filters.get('prov_name').items"
      :editable-file-types="accessScope?.editable_file_types ?? []"
      :editable-industries="accessScope?.editable_industries ?? []"
      @uploaded="refresh"
    />
    <KnowledgeLogsDrawer
      v-model="logTarget.visible"
      :file-id="logTarget.id"
      :file-name="logTarget.name"
    />
  </div>
</template>

<style scoped>
.row-actions { display: inline-flex; align-items: center; gap: 4px; }
.row-action { display: inline-flex; align-items: center; gap: 4px; padding: 0 8px; text-decoration: none; }
.row-action--primary { color: var(--zt-blue-600); }
.row-action--danger { color: var(--zt-danger-text); }
</style>
