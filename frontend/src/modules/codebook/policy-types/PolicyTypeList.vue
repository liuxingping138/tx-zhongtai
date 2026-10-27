<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { computed, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'

import { createPolicyType, importPolicyTypes, listPolicyTypes, updatePolicyType, type PolicyTypeItem } from '@/api/codebook'
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
import { useAuthStore } from '@/stores/auth'
import { EDITOR_GROUPS, SUMMARY_KEYS, TABLE_COLUMNS } from './fields'

/** 和政策三张表同一套组装（见 BaseTagList.vue），交互口径一致：抽屉编辑、409 保留草稿、上传下载按钮共用。 */
const RESOURCE = 'codebook.policy_types'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))

const query = reactive({ keyword: [] as string[], page: 1, page_size: 20 })
const filters = useFilterOptions('/codebook/policy-types')
const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: listPolicyTypes,
  errorText: '加载政策类型失败',
})
const { columns, defaults, selected } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

async function refresh() {
  await Promise.all([load(), filters.load()])
}

const editor = useRecordEditor<PolicyTypeItem>({
  noun: '政策类型',
  groups: EDITOR_GROUPS,
  create: form => createPolicyType({ ...form, type_name: form.type_name ?? '' }),
  update: (row, form) => updatePolicyType(row.id, { ...form, type_name: form.type_name ?? '', version: row.version }),
  refresh,
})

async function onImport(file: File) {
  try {
    const result = await runExcelImport(file, onProgress => importPolicyTypes(file, onProgress))
    reportImportResult(result, '政策类型-跳过明细.xlsx')
    await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

const { exporting, onExport } = useExcelExport({
  path: '/codebook/policy-types/export',
  filename: '政策类型码表.xlsx',
  filters: () => filtersForExport(listQuery.applied),
})

onMounted(() => {
  void load()
  void filters.load()
})
</script>

<template>
  <div>
    <ListPage
      title="政策类型码表"
      hint="维护政策分类及定义，统一业务口径。"
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
          hint="上传 .xlsx 文件，重复或校验不通过的记录会跳过，详情见导入结果。"
          :upload="onImport"
        />
        <ExportButton
          :allowed="auth.canExport(RESOURCE)"
          :loading="exporting"
          @click="onExport"
        />
        <AuditLogButton :module="RESOURCE" />
      </template>
      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          @search="listQuery.search"
          @reset="listQuery.resetFilters"
        >
          <el-form-item label="关键字">
            <FilterSelect
              v-model="query.keyword"
              v-bind="filters.bind('type_name')"
              placeholder="输入或选择政策类型"
            />
          </el-form-item>
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
        :items="items"
        :columns="columns"
        :selected="selected"
        :summary-keys="SUMMARY_KEYS"
        title-key="type_name"
        detail-title="政策类型详情"
        :can-write="canWrite"
        :loading="loading"
        :filtered="resultFiltered"
        @reset="listQuery.resetFilters"
        @edit="editor.openEdit"
      />
    </ListPage>
    <RecordEditorDrawer
      :editor="editor"
      :groups="EDITOR_GROUPS"
    />
  </div>
</template>
