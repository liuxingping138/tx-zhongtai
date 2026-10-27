<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { computed, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'

import {
  createAreaCode,
  importAreaCodes,
  listAreaCodes,
  updateAreaCode,
  type AreaCodeItem,
} from '@/api/codebook'
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

const RESOURCE = 'codebook.area_codes'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))

const query = reactive({
  prov_name: [] as string[],
  city_name: [] as string[],
  county_name: [] as string[],
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/codebook/area-codes')
const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: listAreaCodes,
  errorText: '加载省市区编码表失败',
})
const { columns, defaults, selected } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

async function refresh() {
  await Promise.all([load(), filters.load()])
}

const editor = useRecordEditor<AreaCodeItem>({
  noun: '省市区编码',
  groups: EDITOR_GROUPS,
  create: createAreaCode,
  update: (row, form) => updateAreaCode(row.id, { ...form, version: row.version }),
  refresh,
})

async function onImport(file: File) {
  try {
    const result = await runExcelImport(file, (onProgress) => importAreaCodes(file, onProgress))
    reportImportResult(result, '省市区编码-跳过明细.xlsx')
    await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

const { exporting, onExport } = useExcelExport({
  path: '/codebook/area-codes/export',
  filename: '省市区编码表.xlsx',
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
      title="省市区编码表"
      hint="维护省市区编码、别名与简称。"
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
          hint="按区县编码去重，已有编码会跳过；校验报告列出需处理的记录。"
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
          <el-form-item label="省份">
            <FilterSelect
              v-model="query.prov_name"
              v-bind="filters.bind('prov_name')"
              size="short"
            />
          </el-form-item>
          <el-form-item label="城市">
            <FilterSelect
              v-model="query.city_name"
              v-bind="filters.bind('city_name')"
              size="short"
            />
          </el-form-item>
          <el-form-item label="区县">
            <FilterSelect
              v-model="query.county_name"
              v-bind="filters.bind('county_name')"
              size="short"
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
        :groups="EDITOR_GROUPS"
        :selected="selected"
        :summary-keys="SUMMARY_KEYS"
        title-key="county_name"
        detail-title="省市区详情"
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
      size="560px"
    />
  </div>
</template>
