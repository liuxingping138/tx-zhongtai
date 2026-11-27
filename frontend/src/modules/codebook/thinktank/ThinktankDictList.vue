<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import {
  deleteThinktankDict,
  importThinktankDicts,
  listThinktankDicts,
  type ThinktankDictItem,
  type ThinktankDictSlug,
} from '@/api/codebook'
import { downloadFile } from '@/api/download'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import AuditLogButton from '@/components/AuditLogButton.vue'
import ExportButton from '@/components/ExportButton.vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import ImportButton from '@/components/ImportButton.vue'
import ListEmpty from '@/components/ListEmpty.vue'
import ListPage from '@/components/ListPage.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useListLoader } from '@/composables/useListLoader'
import { filtersForExport } from '@/composables/useListQuery'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import {
  getThinktankDictConfig,
  resolveThinktankDictSlug,
  thinktankDictBasePath,
  thinktankDictExportFilename,
  thinktankDictExportPath,
  thinktankDictSkippedFilename,
} from './configs'
import ThinktankDictFormDialog from './ThinktankDictFormDialog.vue'
import { useThinktankDictOptions } from './useThinktankDictOptions'
import { useThinktankDictQuery } from './useThinktankDictQuery'

const props = defineProps<{ slug?: ThinktankDictSlug }>()
const route = useRoute()
const auth = useAuthStore()

const activeSlug = computed<ThinktankDictSlug>(() => resolveThinktankDictSlug(props.slug, route.meta?.dictSlug))
const config = computed(() => getThinktankDictConfig(activeSlug.value))
const resource = computed(() => config.value.resource)
const basePath = computed(() => thinktankDictBasePath(activeSlug.value))
const canWrite = computed(() => auth.canFull(resource.value))
const canExport = computed(() => auth.canExport(resource.value))
const importHint = computed(
  () => `上传 .xlsx 文件（列头为「${config.value.fieldLabel}」），空白或重复记录会自动跳过，详情见导入结果。`,
)

const listQuery = useThinktankDictQuery((): Promise<void> => load())
const { query, applied } = listQuery
const filters = useThinktankDictOptions(basePath)
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: params => listThinktankDicts(activeSlug.value, params),
  errorText: '加载码表数据失败',
})

const dialogVisible = ref(false)
const editingItem = ref<ThinktankDictItem | null>(null)
const deletingId = ref('')
const exporting = ref(false)

async function refresh(): Promise<void> {
  await Promise.all([load(), filters.load()])
}

function openCreate(): void {
  editingItem.value = null
  dialogVisible.value = true
}

function openEdit(row: ThinktankDictItem): void {
  editingItem.value = row
  dialogVisible.value = true
}

async function onSaved(): Promise<void> {
  await refresh()
}

async function onDelete(row: ThinktankDictItem): Promise<void> {
  if (deletingId.value) return
  const label = config.value.fieldLabel
  const confirmed = await ElMessageBox.confirm(
    `确定要删除${label}「${row.name}」吗？删除后无法恢复。`,
    `删除${label}`,
    {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger',
    },
  ).then(() => true, () => false)
  if (!confirmed) return
  const slug = activeSlug.value
  deletingId.value = row.id
  try {
    await deleteThinktankDict(slug, row.id)
    ElMessage.success('已删除')
    if (activeSlug.value === slug) {
      if (items.value.length === 1 && query.page > 1) query.page -= 1
      await refresh()
    }
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败'))
  } finally {
    deletingId.value = ''
  }
}

async function onImport(file: File): Promise<boolean> {
  const slug = activeSlug.value
  const currentConfig = config.value
  try {
    const result = await runExcelImport(file, onProgress => importThinktankDicts(slug, file, onProgress))
    reportImportResult(result, thinktankDictSkippedFilename(currentConfig))
    if (activeSlug.value === slug) await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

async function onExport(): Promise<void> {
  if (exporting.value) return
  exporting.value = true
  try {
    await downloadFile(
      thinktankDictExportPath(activeSlug.value),
      thinktankDictExportFilename(config.value),
      filtersForExport(applied),
    )
    ElMessage.success('下载已开始，请查看浏览器下载列表')
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败，请重试'))
  } finally {
    exporting.value = false
  }
}

watch(activeSlug, () => {
  dialogVisible.value = false
  editingItem.value = null
  deletingId.value = ''
  listQuery.syncForSlugChange()
  items.value = []
  total.value = 0
  loadError.value = ''
  resultFiltered.value = false
  filters.reset()
  void refresh()
})

onMounted(() => {
  void refresh()
})
</script>

<template>
  <div class="thinktank-dict-page">
    <ListPage
      :title="config.title"
      :hint="config.hint"
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
          @click="openCreate"
        >
          新增
        </el-button>
        <ImportButton
          v-if="canWrite"
          :hint="importHint"
          :upload="onImport"
        />
        <ExportButton
          :allowed="canExport"
          :loading="exporting"
          @click="onExport"
        />
        <AuditLogButton :module="resource" />
      </template>

      <template #filters>
        <FilterBar
          :query="query"
          :applied="applied"
          @search="listQuery.search"
          @reset="listQuery.resetFilters"
        >
          <el-form-item :label="config.fieldLabel">
            <FilterSelect
              v-model="query.keyword"
              v-bind="filters.bind('name')"
              :placeholder="`输入或选择${config.fieldLabel}`"
            />
          </el-form-item>
        </FilterBar>
      </template>

      <TableSkeleton
        v-if="loading && items.length === 0"
        :columns="6"
        :has-actions="canWrite"
      />
      <el-table
        v-else
        class="data-table"
        :class="{ 'is-refreshing': loading }"
        :data="items"
        row-key="id"
        stripe
      >
        <template #empty>
          <ListEmpty
            :loading="loading"
            :filtered="resultFiltered"
            @reset="listQuery.resetFilters"
          />
        </template>
        <el-table-column
          label="序号"
          width="72"
          align="center"
        >
          <template #default="{ $index }">
            <span class="dict-seq">{{ (query.page - 1) * query.page_size + $index + 1 }}</span>
          </template>
        </el-table-column>
        <el-table-column
          :label="config.fieldLabel"
          prop="name"
          min-width="220"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span class="dict-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="入库时间"
          min-width="180"
        >
          <template #default="{ row }">
            <span class="dict-meta">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="入库人"
          min-width="130"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span class="dict-meta">{{ row.created_by_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="更新时间"
          min-width="180"
        >
          <template #default="{ row }">
            <span class="dict-meta">{{ formatTime(row.updated_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="操作人"
          min-width="130"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span class="dict-meta">{{ row.updated_by_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-if="canWrite"
          label="操作"
          width="144"
          class-name="table-action"
        >
          <template #default="{ row }">
            <div class="row-actions">
              <button
                type="button"
                class="row-action row-action--primary"
                :disabled="deletingId === row.id"
                @click="openEdit(row)"
              >
                编辑
              </button>
              <button
                type="button"
                class="row-action row-action--danger"
                :disabled="Boolean(deletingId)"
                @click="onDelete(row)"
              >
                {{ deletingId === row.id ? '删除中…' : '删除' }}
              </button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </ListPage>

    <ThinktankDictFormDialog
      v-model="dialogVisible"
      :slug="activeSlug"
      :config="config"
      :item="editingItem"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.dict-seq {
  color: var(--zt-ink-500);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.dict-name {
  color: var(--zt-ink-900);
  font-weight: 550;
}

.dict-meta {
  color: var(--zt-ink-500);
  font-size: 13px;
}

.is-refreshing {
  opacity: 0.65;
  pointer-events: none;
  transition: opacity 0.2s ease;
}
</style>
