<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  getInterpretation,
  importInterpretations,
  listInterpretations,
  setInterpretationsDataStatus,
  type InterpretationItem,
} from '@/api/policy'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import AuditLogButton from '@/components/AuditLogButton.vue'
import BatchChoiceDialog from '@/components/BatchChoiceDialog.vue'
import BusinessTable from '@/components/BusinessTable.vue'
import { reviewQuery } from '../shared/reviewQuery'
import ColumnPicker from '@/components/ColumnPicker.vue'
import ExportButton from '@/components/ExportButton.vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterChipSelect from '@/components/FilterChipSelect.vue'
import FilterKeyword from '@/components/FilterKeyword.vue'
import ImportButton from '@/components/ImportButton.vue'
import ListPage from '@/components/ListPage.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useExcelExport } from '@/composables/useExcelExport'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useListLoader } from '@/composables/useListLoader'
import { filtersForExport, useListQuery } from '@/composables/useListQuery'
import { useTableSelection } from '@/composables/useTableSelection'
import { useAuthStore } from '@/stores/auth'
import { useListRetagPoll } from '../base-tags/retag'
import RetagDialog from '../base-tags/RetagDialog.vue'
import { EDITOR_GROUPS, mergeInterpretAiColumns, SUMMARY_KEYS, TABLE_COLUMNS } from './fields'

const RESOURCE = 'policy.interpretations'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))

const query = reactive({
  policy_title: [] as string[],
  industry_l1: [] as string[],
  scenario_l1_name: [] as string[],
  opportunity_type: [] as string[],
  is_new_scenario: [] as string[],
  new_scenario_level: [] as string[],
  info_level: [] as string[],
  data_status: [] as string[],
  scenario_state: [] as string[],
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
const { columns: baseColumns, defaults, selected } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)
const columns = computed(() => mergeInterpretAiColumns(baseColumns, filters.aiFields.value))

async function refresh() {
  await Promise.all([load(), filters.load()])
}

// AI 写的行都是「待验证」：人工核对完勾选多条，一次改成「人工验证」。
const selection = useTableSelection<InterpretationItem>()
const checked = selection.checked
const statusOpen = ref(false)
const retagOpen = ref(false)
const { retagging, progress: retagProgress, startAfterRetag } = useListRetagPoll(load, getInterpretation)
const STATUS_CHOICES = [
  { value: '人工验证', label: '人工验证', hint: '核对过、内容可用。之后 AI 重新解读、回填市场机会都不会再覆盖这些行。新增场景进不进码表在「新增场景审核」里按场景决定，和这里无关。' },
  { value: '待验证', label: '待验证', hint: '退回待核对。AI 重新解读时可以替换这些行。' },
]
async function submitStatus(status: string) {
  const result = await setInterpretationsDataStatus(selection.ids.value, status)
  return { message: `已改 ${result.updated} 条${result.unchanged ? `，${result.unchanged} 条原本就是「${status}」` : ''}` }
}
async function afterStatus() {
  selection.clear()
  await refresh()
}
async function afterRetag() {
  const ids = [...selection.ids.value]
  selection.clear()
  await startAfterRetag(ids)
}
// 标题和「查看」进核对页：带上已生效的筛选和这条的位置，那边能翻上一条、下一条，读完就标人工验证。
function detailRoute(row: InterpretationItem, index: number) {
  const position = (query.page - 1) * query.page_size + index
  return { name: 'policy-interpretation-review', params: { id: row.id }, query: reviewQuery(listQuery.applied, position, query.page_size) }
}

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
  filename: '政策解读列表.xlsx',
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
      title="政策解读列表"
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
        <!-- 勾选了才出现，平时不摆灰按钮（后端要求 policy.base_tags:update） -->
        <el-button
          v-if="auth.canFull('policy.base_tags') && (checked.length || retagging)"
          :loading="retagging"
          @click="retagOpen = true"
        >
          {{ retagging ? `正在重新打标（${retagProgress.done}/${retagProgress.total}）…` : `重新打标（${checked.length}）` }}
        </el-button>
        <el-button
          v-if="canWrite && checked.length"
          @click="statusOpen = true"
        >
          批量改数据状态（{{ checked.length }}）
        </el-button>
        <AuditLogButton :module="RESOURCE" />
      </template>
      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          variant="chips"
          :more-keys="['is_new_scenario', 'new_scenario_level', 'info_level']"
          @search="listQuery.search"
          @reset="listQuery.resetFilters"
        >
          <template #search>
            <FilterKeyword
              v-model="query.policy_title"
              label="政策原文名称"
              placeholder="搜索政策原文名称关键词…"
              class="filter-search-main"
            />
          </template>
          <FilterChipSelect
            v-model="query.industry_l1"
            label="一级行业"
            v-bind="filters.bind('industry_l1')"
          />
          <FilterChipSelect
            v-model="query.scenario_l1_name"
            label="一级场景"
            v-bind="filters.bind('scenario_l1_name')"
          />
          <FilterChipSelect
            v-model="query.scenario_state"
            label="场景状态"
            v-bind="filters.bind('scenario_state')"
          />
          <FilterChipSelect
            v-model="query.data_status"
            label="数据状态"
            v-bind="filters.bind('data_status')"
          />
          <FilterChipSelect
            v-model="query.opportunity_type"
            label="机会类型"
            v-bind="filters.bind('opportunity_type')"
          />
          <template #more>
            <FilterChipSelect
              v-model="query.is_new_scenario"
              label="是否新增场景"
              v-bind="filters.bind('is_new_scenario')"
            />
            <FilterChipSelect
              v-model="query.new_scenario_level"
              label="新增场景级别"
              v-bind="filters.bind('new_scenario_level')"
            />
            <FilterChipSelect
              v-model="query.info_level"
              label="信息化等级"
              v-bind="filters.bind('info_level')"
            />
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
        title-key="policy_title"
        :detail-route="detailRoute"
        :can-write="canWrite"
        :loading="loading"
        :filtered="resultFiltered"
        @reset="listQuery.resetFilters"
        @selection-change="checked = $event"
      />
    </ListPage>
    <BatchChoiceDialog
      v-model="statusOpen"
      title="批量改数据状态"
      :count="checked.length"
      prompt="数据状态改为："
      :choices="STATUS_CHOICES"
      :submit="submitStatus"
      @done="afterStatus"
    />
    <RetagDialog
      v-model="retagOpen"
      :ids="selection.ids.value"
      default-step="interpret"
      @done="afterRetag"
    />
  </div>
</template>

