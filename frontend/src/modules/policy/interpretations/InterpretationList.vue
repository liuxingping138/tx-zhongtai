<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { computed, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'

import {
  createInterpretation,
  importInterpretations,
  listInterpretations,
  updateInterpretation,
  type InterpretationItem,
} from '@/api/policy'
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
import { EDITOR_DEFAULTS, EDITOR_GROUPS, SUMMARY_KEYS, TABLE_COLUMNS } from './fields'

const RESOURCE = 'policy.interpretations'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))

const query = reactive({
  policy_title: [] as string[],
  industry_scenario_code: [] as string[],
  industry_l1: [] as string[],
  scenario_l1_name: [] as string[],
  opportunity_type: [] as string[],
  is_new_scenario: [] as string[],
  new_scenario_level: [] as string[],
  info_level: [] as string[],
  data_status: [] as string[],
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/policy/interpretations')
const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: listInterpretations,
  errorText: '加载政策解读失败',
})
const { columns, defaults, selected } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

async function refresh() {
  await Promise.all([load(), filters.load()])
}

const editor = useRecordEditor<InterpretationItem>({
  noun: '政策解读',
  groups: EDITOR_GROUPS,
  defaults: EDITOR_DEFAULTS,
  create: createInterpretation,
  // 政策唯一标识不在表单里，按原值提交。
  update: (row, form) => updateInterpretation(row.id, { ...form, policy_uid: row.policy_uid, version: row.version }),
  refresh,
})

async function onImport(file: File) {
  try {
    const result = await runExcelImport(file, (onProgress) => importInterpretations(file, onProgress))
    reportImportResult(result, '政策解读-跳过明细.xlsx')
    await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

const { exporting, onExport } = useExcelExport({
  path: '/policy/interpretations/export',
  filename: '政策解读表.xlsx',
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
      title="政策解读表"
      hint="关联行业场景，整理政策解读与业务机会。"
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
          hint="政策标识与关联主键可自动生成；重复或校验不通过的记录会跳过并提供报告。"
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
          <el-form-item label="政策原文名称">
            <FilterSelect
              v-model="query.policy_title"
              v-bind="filters.bind('policy_title')"
            />
          </el-form-item>
          <el-form-item label="行业场景编码">
            <FilterSelect
              v-model="query.industry_scenario_code"
              v-bind="filters.bind('industry_scenario_code')"
            />
          </el-form-item>
          <el-form-item label="一级行业">
            <FilterSelect
              v-model="query.industry_l1"
              v-bind="filters.bind('industry_l1')"
              size="short"
            />
          </el-form-item>
          <el-form-item label="一级场景">
            <FilterSelect
              v-model="query.scenario_l1_name"
              v-bind="filters.bind('scenario_l1_name')"
              size="short"
            />
          </el-form-item>
          <template #advanced>
            <el-form-item label="是否新增场景">
              <FilterSelect
                v-model="query.is_new_scenario"
                v-bind="filters.bind('is_new_scenario')"
                size="short"
              />
            </el-form-item>
            <el-form-item label="新增场景级别">
              <FilterSelect
                v-model="query.new_scenario_level"
                v-bind="filters.bind('new_scenario_level')"
                size="short"
              />
            </el-form-item>
            <el-form-item label="信息化等级">
              <FilterSelect
                v-model="query.info_level"
                v-bind="filters.bind('info_level')"
                size="short"
              />
            </el-form-item>
            <el-form-item label="数据状态">
              <FilterSelect
                v-model="query.data_status"
                v-bind="filters.bind('data_status')"
                size="short"
              />
            </el-form-item>
            <el-form-item label="机会类型">
              <FilterSelect
                v-model="query.opportunity_type"
                v-bind="filters.bind('opportunity_type')"
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
        :selected="selected"
        :summary-keys="SUMMARY_KEYS"
        title-key="policy_title"
        detail-title="政策解读详情"
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
