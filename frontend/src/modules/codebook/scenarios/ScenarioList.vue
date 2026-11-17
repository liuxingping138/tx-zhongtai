<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { computed, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'

import {
  createScenario,
  importScenarios,
  listScenarios,
  updateScenario,
  type ScenarioItem,
} from '@/api/codebook'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import AuditLogButton from '@/components/AuditLogButton.vue'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import ExportButton from '@/components/ExportButton.vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterKeyword from '@/components/FilterKeyword.vue'
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

const RESOURCE = 'codebook.scenarios'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))

const query = reactive({
  // 按场景名称查（一级、二级、三级任一包含），不让人输 20 位编码（2026-11-03）
  scenario_name: [] as string[],
  industry_l1: [] as string[],
  scenario_tag: [] as string[],
  customer_group_name: [] as string[],
  is_new_scenario: [] as string[],
  enrich_status: [] as string[],
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/codebook/scenarios')
const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: listScenarios,
  errorText: '加载行业场景码表失败',
})
const { columns, defaults, selected } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

async function refresh() {
  await Promise.all([load(), filters.load()])
}

const editor = useRecordEditor<ScenarioItem>({
  noun: '行业场景',
  groups: EDITOR_GROUPS,
  create: createScenario,
  update: (row, form) => updateScenario(row.id, { ...form, version: row.version }),
  refresh,
})

async function onImport(file: File) {
  try {
    const result = await runExcelImport(file, (onProgress) => importScenarios(file, onProgress))
    reportImportResult(result, '行业场景-跳过明细.xlsx')
    await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

const { exporting, onExport } = useExcelExport({
  path: '/codebook/scenarios/export',
  filename: '行业场景字典表.xlsx',
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
      title="行业场景码表"
      hint="统一行业、场景、客群和产品信息。"
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
          hint="按整行内容去重，重复记录会跳过；导入完成后可查看结果和校验报告。"
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
          <el-form-item label="场景名称">
            <FilterKeyword
              v-model="query.scenario_name"
              label="场景名称"
              placeholder="输入场景名称关键词，一二三级都查"
            />
          </el-form-item>
          <el-form-item label="一级行业">
            <FilterSelect
              v-model="query.industry_l1"
              v-bind="filters.bind('industry_l1')"
              size="short"
            />
          </el-form-item>
          <el-form-item label="场景标签">
            <FilterSelect
              v-model="query.scenario_tag"
              v-bind="filters.bind('scenario_tag')"
            />
          </el-form-item>
          <template #advanced>
            <el-form-item label="客群名称">
              <FilterSelect
                v-model="query.customer_group_name"
                v-bind="filters.bind('customer_group_name')"
              />
            </el-form-item>
            <el-form-item label="是否新增场景">
              <FilterSelect
                v-model="query.is_new_scenario"
                v-bind="filters.bind('is_new_scenario')"
                size="short"
              />
            </el-form-item>
            <el-form-item label="补充状态">
              <FilterSelect
                v-model="query.enrich_status"
                v-bind="filters.bind('enrich_status')"
                size="short"
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
        :items="items"
        :columns="columns"
        :groups="EDITOR_GROUPS"
        :selected="selected"
        :summary-keys="SUMMARY_KEYS"
        title-key="scenario_tag"
        detail-title="行业场景详情"
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
