<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  createInterpretation,
  importInterpretations,
  listInterpretations,
  setInterpretationsDataStatus,
  updateInterpretation,
  type InterpretationItem,
} from '@/api/policy'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import AuditLogButton from '@/components/AuditLogButton.vue'
import BatchChoiceDialog from '@/components/BatchChoiceDialog.vue'
import SyncScenariosButton from './SyncScenariosButton.vue'
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
import { useTableSelection } from '@/composables/useTableSelection'
import { useAuthStore } from '@/stores/auth'
import { EDITOR_DEFAULTS, EDITOR_GROUPS, SUMMARY_KEYS, TABLE_COLUMNS } from './fields'

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

// 改成「人工验证」、导入之后，同步按钮上的待同步条数要跟着变。
const scenarioSync = ref<InstanceType<typeof SyncScenariosButton>>()
async function refresh() {
  await Promise.all([load(), filters.load(), scenarioSync.value?.refresh()])
}

// AI 写的行都是「待验证」：人工核对完勾选多条，一次改成「人工验证」。
const selection = useTableSelection<InterpretationItem>()
const checked = selection.checked
const statusOpen = ref(false)
const STATUS_CHOICES = [
  { value: '人工验证', label: '人工验证', hint: '核对过、内容可用。之后 AI 重新解读、回填市场机会都不会再覆盖这些行；新增场景改成人工验证后才能同步进码表。' },
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
// 在详情里读完就能标：不用关掉抽屉再回列表勾选。
const verifying = ref(false)
async function markVerified(row: InterpretationItem, close: () => void) {
  verifying.value = true
  try {
    await setInterpretationsDataStatus([row.id], '人工验证')
    ElMessage.success('已标为人工验证')
    close()
    await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '没能改成人工验证，请重试'))
  } finally {
    verifying.value = false
  }
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
        <el-button
          v-if="canWrite"
          :disabled="!checked.length"
          @click="statusOpen = true"
        >
          批量改数据状态{{ checked.length ? `（${checked.length}）` : '' }}
        </el-button>
        <SyncScenariosButton
          v-if="canWrite"
          ref="scenarioSync"
          @synced="load"
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
            <FilterKeyword
              v-model="query.policy_title"
              label="政策原文名称"
              placeholder="输入政策名称关键词"
              @search="listQuery.search"
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
        :ref="selection.bindTable"
        :items="items"
        :selectable="canWrite"
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
        @selection-change="checked = $event"
      >
        <template #detail-actions="{ row, close }">
          <el-button
            v-if="canWrite && row.data_status !== '人工验证'"
            :loading="verifying"
            @click="markVerified(row, close)"
          >
            标为人工验证
          </el-button>
        </template>
      </BusinessTable>
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
    <RecordEditorDrawer
      :editor="editor"
      :groups="EDITOR_GROUPS"
    />
  </div>
</template>
