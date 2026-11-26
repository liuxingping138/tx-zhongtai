<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { importAfterAreaResolve } from '@/api/codebook'
import { getBaseTag, importBaseTags, listBaseTags, type BaseTagItem } from '@/api/policy'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import AuditLogButton from '@/components/AuditLogButton.vue'
import BusinessTable from '@/components/BusinessTable.vue'
import { reviewQuery } from '../shared/reviewQuery'
import ColumnPicker from '@/components/ColumnPicker.vue'
import ExportButton from '@/components/ExportButton.vue'
import FilterBar from '@/components/FilterBar.vue'
import FilterKeyword from '@/components/FilterKeyword.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import ImportButton from '@/components/ImportButton.vue'
import ListPage from '@/components/ListPage.vue'
import { useDetailColumns } from '@/composables/useDetailColumns'
import { useExcelExport } from '@/composables/useExcelExport'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useListLoader } from '@/composables/useListLoader'
import { filtersForExport, useListQuery } from '@/composables/useListQuery'
import { useTableSelection } from '@/composables/useTableSelection'
import { useAuthStore } from '@/stores/auth'
import { AI_STATUS_CHOICES, EDITOR_GROUPS, SUMMARY_KEYS, TABLE_COLUMNS, mergeAiColumns } from './fields'
import { useListRetagPoll, type RetagSubmitOutcome } from './retag'
import RetagDialog from './RetagDialog.vue'

const RESOURCE = 'policy.base_tags'
const auth = useAuthStore()
const canWrite = computed(() => auth.canFull(RESOURCE))
// 上传要先经省市区编码表补地区编码（codebook.area_codes:resolve 是它的查看档）：没这项权限的角色点了只会报「没有权限」，提前说清。
const importBlocked = computed(() =>
  auth.canRead('codebook.area_codes') ? '' : '上传要靠省市区编码表补地区编码，当前角色没有它的查看权限，请找管理员开通',
)

const query = reactive({
  policy_name: [] as string[],
  province_name: [] as string[],
  policy_types: [] as string[],
  is_policy: [] as string[],
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
const { columns: baseColumns, defaults, selected } = useDetailColumns(TABLE_COLUMNS, EDITOR_GROUPS)
const columns = computed(() => mergeAiColumns(baseColumns, filters.aiFields.value))

async function refresh() {
  await Promise.all([load(), filters.load()])
}
// 标题和「查看」进核对页：带上已生效的筛选和这条的位置，那边能翻上一条、下一条。
function detailRoute(row: BaseTagItem, index: number) {
  const position = (query.page - 1) * query.page_size + index
  return { name: 'policy-base-tag-review', params: { id: row.id }, query: reviewQuery(listQuery.applied, position, query.page_size) }
}

// 打失败的、或模板改好后想重打的：按「打标状态」筛出来，勾选后放回某个任务的待办。
const selection = useTableSelection<BaseTagItem>()
const checked = selection.checked
const retagOpen = ref(false)
const { retagging, progress: retagProgress, startAfterRetag } = useListRetagPoll(load, getBaseTag)
async function afterRetag(result: RetagSubmitOutcome) {
  const ids = [...selection.ids.value]
  selection.clear()
  if (result.queued > 0 && result.triggered) {
    await startAfterRetag(ids)
  } else if (result.queued > 0) {
    await load()
  }
}

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
        <ImportButton
          v-if="canWrite"
          hint="上传后关联省市区编码，任一条记录关联失败则整批退回，详情见校验报告。"
          :upload="onImport"
          :blocked="importBlocked"
        />
        <ExportButton
          :allowed="auth.canExport(RESOURCE)"
          :loading="exporting"
          @click="onExport"
        />
        <!-- 勾选了才出现，平时不摆灰按钮 -->
        <el-button
          v-if="canWrite && (checked.length || retagging)"
          :loading="retagging"
          @click="retagOpen = true"
        >
          {{ retagging ? `正在重新打标（${retagProgress.done}/${retagProgress.total}）…` : `重新打标（${checked.length}）` }}
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
            <el-form-item label="是否政策">
              <FilterSelect
                v-model="query.is_policy"
                :options="['是', '否', '疑似']"
                size="short"
              />
            </el-form-item>
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
        :groups="EDITOR_GROUPS"
        :selected="selected"
        :summary-keys="SUMMARY_KEYS"
        title-key="policy_name"
        :detail-route="detailRoute"
        :can-write="canWrite"
        :loading="loading"
        :filtered="resultFiltered"
        @reset="listQuery.resetFilters"
        @selection-change="checked = $event"
      />
    </ListPage>
    <RetagDialog
      v-model="retagOpen"
      :ids="selection.ids.value"
      @done="afterRetag"
    />
  </div>
</template>

