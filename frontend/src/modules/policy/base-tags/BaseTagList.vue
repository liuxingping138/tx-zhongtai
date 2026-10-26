<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { importAfterAreaResolve } from '@/api/codebook'
import { requestRetag, type AiTaskCode } from '@/api/aiTagging'
import { createBaseTag, importBaseTags, listBaseTags, updateBaseTag, type BaseTagItem } from '@/api/policy'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import AuditLogButton from '@/components/AuditLogButton.vue'
import BatchChoiceDialog from '@/components/BatchChoiceDialog.vue'
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
import { AI_STATUS_CHOICES, EDITOR_GROUPS, RETAG_CHOICES, SUMMARY_KEYS, TABLE_COLUMNS } from './fields'

const RESOURCE = 'policy.base_tags'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))

const query = reactive({
  policy_name: [] as string[],
  province_name: [] as string[],
  policy_types: [] as string[],
  is_penetrate: [] as string[],
  need_interpret: [] as string[],
  ai_status: [] as string[],
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/policy/base-tags')
const listQuery = useListQuery(query, (): Promise<void> => load())
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: listBaseTags,
  errorText: '加载政策基础标签失败',
})
const { columns, defaults, selected } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)

async function refresh() {
  await Promise.all([load(), filters.load()])
}

// 打失败的、或模板改好后想重打的：按「打标状态」筛出来，勾选后放回某个任务的待办。
const selection = useTableSelection<BaseTagItem>()
const checked = selection.checked
const retagOpen = ref(false)
async function submitRetag(step: string) {
  const result = await requestRetag(selection.ids.value, step as AiTaskCode)
  const message = result.queued
    ? `已把 ${result.queued} 条放回「${result.task}」的待办，到任务调度执行它或等每日计划`
    : '没有可以重新打标的政策'
  return { message, skipped: result.skipped }
}
async function afterRetag() {
  selection.clear()
  await refresh()
}

const editor = useRecordEditor<BaseTagItem>({
  noun: '政策基础标签',
  groups: EDITOR_GROUPS,
  create: createBaseTag,
  update: (row, form) => updateBaseTag(row.id, { ...form, version: row.version }),
  refresh,
})

async function onImport(file: File) {
  try {
    const result = await runExcelImport(file, (onProgress) =>
      importAfterAreaResolve(file, importBaseTags, onProgress),
    )
    reportImportResult(result, '政策基础标签-上传校验.xlsx')
    if (!result.rejected) await refresh()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

const { exporting, onExport } = useExcelExport({
  path: '/policy/base-tags/export',
  filename: '政策基础标签表.xlsx',
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
      title="政策基础标签表"
      hint="维护政策基础信息、地区归属与业务标签。"
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
          hint="上传后关联省市区编码，任一条记录关联失败则整批退回，详情见校验报告。"
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
          @click="retagOpen = true"
        >
          重新打标{{ checked.length ? `（${checked.length}）` : '' }}
        </el-button>
        <AuditLogButton :module="RESOURCE" />
      </template>
      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          @search="listQuery.search"
          @reset="listQuery.resetFilters"
        >
          <el-form-item label="政策名称">
            <FilterKeyword
              v-model="query.policy_name"
              label="政策名称"
              placeholder="输入政策名称关键词"
              @search="listQuery.search"
            />
          </el-form-item>
          <el-form-item label="省份">
            <FilterSelect
              v-model="query.province_name"
              v-bind="filters.bind('province_name')"
              size="short"
            />
          </el-form-item>
          <el-form-item label="政策类型">
            <FilterSelect
              v-model="query.policy_types"
              v-bind="filters.bind('policy_types')"
            />
          </el-form-item>
          <template #advanced>
            <el-form-item label="是否穿透">
              <FilterSelect
                v-model="query.is_penetrate"
                v-bind="filters.bind('is_penetrate')"
                size="short"
              />
            </el-form-item>
            <el-form-item label="是否解读">
              <FilterSelect
                v-model="query.need_interpret"
                v-bind="filters.bind('need_interpret')"
                size="short"
              />
            </el-form-item>
            <el-form-item label="打标状态">
              <FilterSelect
                v-model="query.ai_status"
                :options="AI_STATUS_CHOICES"
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
        title-key="policy_name"
        detail-title="政策基础标签详情"
        :can-write="canWrite"
        :loading="loading"
        :filtered="resultFiltered"
        @reset="listQuery.resetFilters"
        @edit="editor.openEdit"
        @selection-change="checked = $event"
      />
    </ListPage>
    <BatchChoiceDialog
      v-model="retagOpen"
      title="重新打标"
      :count="checked.length"
      prompt="重新打标的是："
      :choices="RETAG_CHOICES"
      :submit="submitRetag"
      @done="afterRetag"
    />
    <RecordEditorDrawer
      :editor="editor"
      :groups="EDITOR_GROUPS"
    />
  </div>
</template>

