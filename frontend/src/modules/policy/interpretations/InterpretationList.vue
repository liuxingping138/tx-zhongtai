<script setup lang="ts">
import { Plus, Upload, Download, Clock } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  createInterpretation,
  importInterpretations,
  listInterpretations,
  updateInterpretation,
  type InterpretationItem,
} from '@/api/policy'
import { errorMessage, isApiError } from '@/api/errors'
import { importUi, reportImportResult, runExcelImport } from '@/api/excelImport'
import FilterSelect from '@/components/FilterSelect.vue'
import ListPage from '@/components/ListPage.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useExcelExport } from '@/composables/useExcelExport'
import { useListLoader } from '@/composables/useListLoader'
import { filtersForExport, useListQuery } from '@/composables/useListQuery'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import GroupedFields, { type EditorGroup } from '@/components/GroupedFields.vue'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
/** 导出单独一档：只读角色能看不能导，按钮保留但禁用并说明原因。 */
const canExport = computed(() => auth.canExport('policy.interpretations'))
const router = useRouter()
const canWrite = computed(() => auth.canFull('policy.interpretations'))
const canAudit = computed(() => auth.canRead('system.audit'))

const emptyForm = {
  tenant_id: '',
  policy_title: '',
  industry_scenario_code: '',
  industry_code: '',
  industry_l1: '',
  industry_l2: '',
  industry_l3: '',
  scenario_code: '',
  scenario_l1_name: '',
  scenario_l2_name: '',
  scenario_l3_name: '',
  target_customers: '',
  opportunity_type: '',
  policy_summary: '',
  has_subsidy: '',
  subsidy_content: '',
  market_opportunity: '',
  info_level: '',
  is_new_scenario: '',
  new_scenario_level: '',
  data_status: '待验证',
}

const DATA_STATUS_CHOICES = ['待验证', '人工验证']

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
const visible = ref(false)
const saving = ref(false)
const saveError = ref('')
const editing = ref<InterpretationItem | null>(null)
const form = reactive({ ...emptyForm })
const filters = useFilterOptions('/policy/interpretations')

const tableColumns = [
  { prop: 'policy_uid', label: '政策唯一标识', width: 300 },
  { prop: 'policy_title', label: '政策原文名称', minWidth: 340, grow: 2 },
  { prop: 'industry_scenario_code', label: '行业场景编码', width: 220 },
  { prop: 'industry_code', label: '行业编码', width: 120 },
  { prop: 'industry_l1', label: '一级行业', width: 120 },
  { prop: 'industry_l2', label: '二级行业', width: 120 },
  { prop: 'industry_l3', label: '三级行业', width: 120 },
  { prop: 'scenario_code', label: '场景编码', width: 140 },
  { prop: 'scenario_l1_name', label: '一级场景名称', minWidth: 140 },
  { prop: 'scenario_l2_name', label: '二级场景名称', minWidth: 140 },
  { prop: 'scenario_l3_name', label: '三级场景名称', minWidth: 140 },
  { prop: 'target_customers', label: '目标客户', fullLabel: '目标客户当前政策影响客户群', minWidth: 260, grow: 1, wrap: true },
  { prop: 'relation_key', label: '关联主键', minWidth: 200 },
  { prop: 'opportunity_type', label: '机会类型', width: 110 },
  { prop: 'policy_summary', label: '政策要文', width: 320, wrap: true },
  { prop: 'has_subsidy', label: '有无政府补贴', width: 120 },
  { prop: 'subsidy_content', label: '补贴内容', minWidth: 180 },
  { prop: 'market_opportunity', label: '政策市场机会', minWidth: 180 },
  { prop: 'info_level', label: '信息化等级', width: 110 },
  { prop: 'is_new_scenario', label: '是否新增场景', width: 120 },
  { prop: 'new_scenario_level', label: '新增场景级别', width: 120 },
  { prop: 'data_status', label: '数据状态', width: 110 },
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
] as const



const listQuery = useListQuery(query, (): Promise<void> => load())

const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: (params) => listInterpretations({
      policy_title: params.policy_title || undefined,
      industry_scenario_code: params.industry_scenario_code || undefined,
      industry_l1: params.industry_l1 || undefined,
      scenario_l1_name: params.scenario_l1_name || undefined,
      opportunity_type: params.opportunity_type || undefined,
      is_new_scenario: params.is_new_scenario || undefined,
      new_scenario_level: params.new_scenario_level || undefined,
      info_level: params.info_level || undefined,
      data_status: params.data_status || undefined,
      page: params.page,
      page_size: params.page_size,
  }),
  errorText: '加载政策解读失败',
})

function onResetFilters() {
  query.policy_title = []
  query.industry_scenario_code = []
  query.industry_l1 = []
  query.scenario_l1_name = []
  query.opportunity_type = []
  query.is_new_scenario = []
  query.new_scenario_level = []
  query.info_level = []
  query.data_status = []
  onSearch()
}

function onSearch() {
  query.page = 1
  listQuery.captureApplied()
  void load()
}

function openCreate() {
  saveError.value = ''
  editing.value = null
  Object.assign(form, emptyForm)
  visible.value = true
}

function openEdit(row: InterpretationItem) {
  saveError.value = ''
  editing.value = row
  Object.assign(form, emptyForm)
  for (const key of Object.keys(emptyForm) as (keyof typeof emptyForm)[]) {
    form[key] = String(row[key] ?? emptyForm[key])
  }
  visible.value = true
}

async function onSave() {
  if (saving.value) return
  saveError.value = ''
  if (!await editorFields.value?.validate()) return
  if (!form.policy_title.trim()) {
    ElMessage.warning('请填写政策原文名称')
    return
  }
  saving.value = true
  try {
    const payload = Object.fromEntries(
      Object.keys(emptyForm).map((key) => [key, form[key as keyof typeof form]]),
    )
    if (editing.value) {
      await updateInterpretation(editing.value.id, { ...payload, policy_uid: editing.value.policy_uid, version: editing.value.version })
    } else {
      await createInterpretation(payload)
    }
    ElMessage.success('已保存')
    visible.value = false
    await Promise.all([load(), filters.load()])
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      saveError.value = '数据已被他人修改或内容重复。请保留需要的内容，关闭后重新打开最新记录再修改。'
      await load()
    } else {
      saveError.value = errorMessage(error, '保存失败，请检查后重试')
    }
  } finally {
    saving.value = false
  }
}

async function onImport(file: File) {
  try {
    const result = await runExcelImport(file, (onProgress) => importInterpretations(file, onProgress))
    reportImportResult(result, '政策解读-跳过明细.xlsx')
    await Promise.all([load(), filters.load()])
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

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'policy.interpretations' } })
}

onMounted(() => {
  void load()
  void filters.load()
})

const editorGroups: EditorGroup[] = [
  {
    "title": "政策与行业",
    "hint": "填写政策名称并关联行业场景，编码请与场景码表保持一致。",
    "fields": [
      {
        "key": "policy_title",
        "label": "政策原文名称",
        "long": true,
        "required": true
      },
      {
        "key": "data_status",
        "label": "数据状态",
        "hint": "新录入默认待验证；人工核对无误后改为人工验证。",
        "required": true,
        "choices": DATA_STATUS_CHOICES
      },
      {
        "key": "tenant_id",
        "label": "租户标识",
        "hint": "对应数据所属租户，无租户标识时可留空。",
        "maxLength": 64
      },
      {
        "key": "industry_scenario_code",
        "label": "行业场景编码",
        "long": false,
        "required": false,
        "maxLength": 128
      },
      {
        "key": "industry_code",
        "label": "行业编码",
        "long": false,
        "required": false,
        "maxLength": 32
      },
      {
        "key": "industry_l1",
        "label": "一级行业",
        "long": false,
        "required": false,
        "maxLength": 128
      },
      {
        "key": "industry_l2",
        "label": "二级行业",
        "long": false,
        "required": false,
        "maxLength": 128
      },
      {
        "key": "industry_l3",
        "label": "三级行业",
        "long": false,
        "required": false,
        "maxLength": 128
      }
    ]
  },
  {
    "title": "场景信息",
    "hint": "补充场景层级；新增场景时填写相应级别。",
    "fields": [
      {
        "key": "scenario_code",
        "label": "场景编码",
        "long": false,
        "required": false,
        "maxLength": 64
      },
      {
        "key": "scenario_l1_name",
        "label": "一级场景名称",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "scenario_l2_name",
        "label": "二级场景名称",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "scenario_l3_name",
        "label": "三级场景名称",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "is_new_scenario",
        "label": "是否新增场景",
        "long": false,
        "required": false,
        "maxLength": 32
      },
      {
        "key": "new_scenario_level",
        "label": "新增场景级别",
        "long": false,
        "required": false,
        "maxLength": 64
      }
    ]
  },
  {
    "title": "解读与业务机会",
    "hint": "先概括政策内容，再描述目标客户、补贴及市场机会。",
    "fields": [
      {
        "key": "policy_summary",
        "label": "政策要文",
        "long": true,
        "required": false
      },
      {
        "key": "target_customers",
        "label": "目标客户当前政策影响客户群",
        "long": true,
        "required": false
      },
      {
        "key": "opportunity_type",
        "label": "机会类型",
        "long": false,
        "required": false,
        "maxLength": 64
      },
      {
        "key": "has_subsidy",
        "label": "有无政府补贴",
        "long": false,
        "required": false,
        "maxLength": 32
      },
      {
        "key": "subsidy_content",
        "label": "补贴内容",
        "long": true,
        "required": false
      },
      {
        "key": "market_opportunity",
        "label": "政策市场机会",
        "long": true,
        "required": false
      },
      {
        "key": "info_level",
        "label": "信息化等级",
        "long": false,
        "required": false,
        "maxLength": 32
      }
    ]
  }
]
const editorFields = ref<InstanceType<typeof GroupedFields>>()
const editorGuard = useUnsavedForm(visible, () => form, saving)

const legacyDefaults = ['policy_title', 'opportunity_type', 'target_customers', 'has_subsidy']

const detailColumns = computed(() => {
  const known = new Set(tableColumns.map(col => String(col.prop)))
  return [...tableColumns, ...editorGroups.flatMap(group => group.fields).filter(field => !known.has(field.key)).map(field => ({ prop: field.key, label: field.label }))]
})
const defaultColumns = computed(() => detailColumns.value.map(col => col.prop))
const selectedColumns = ref([...defaultColumns.value])
const NO_EXPORT_HINT = '你的角色没有导出权限，如需下载 Excel 请联系管理员开通「导出」。'
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
          @click="openCreate"
        >
          新增
        </el-button>
        <el-upload
          v-if="canWrite"
          :show-file-list="false"
          accept=".xlsx"
          :before-upload="onImport"
        >
          <el-tooltip
            content="政策标识与关联主键可自动生成；重复或校验不通过的记录会跳过并提供报告。"
            placement="bottom"
          >
            <el-button
              :icon="Upload"
              :disabled="importUi.visible"
            >
              上传 Excel
            </el-button>
          </el-tooltip>
        </el-upload>
        <el-tooltip
          :content="canExport ? '按当前已生效的筛选条件导出；未筛选时导出全表。' : NO_EXPORT_HINT"
          placement="bottom"
        >
          <span>
            <el-button
              :icon="Download"
              :loading="exporting"
              :disabled="!canExport"
              @click="onExport"
            >
              下载 Excel
            </el-button>
          </span>
        </el-tooltip>
        <el-button
          v-if="canAudit"
          :icon="Clock"
          @click="openLogs"
        >
          操作记录
        </el-button>
      </template>
      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          @search="onSearch"
          @reset="onResetFilters"
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
          v-model="selectedColumns"
          :columns="detailColumns"
          :defaults="defaultColumns"
          :legacy-defaults="legacyDefaults"
        />
      </template>
      <BusinessTable
        :items="items"
        :columns="detailColumns"
        :selected="selectedColumns"
        :summary-keys="legacyDefaults"
        title-key="policy_title"
        detail-title="政策解读详情"
        :can-write="canWrite"
        :loading="loading"
        :filtered="resultFiltered"
        @reset="onResetFilters"
        @edit="openEdit"
      />
    </ListPage>
    <el-drawer
      v-model="visible"
      class="editor-overlay"
      destroy-on-close
      :before-close="editorGuard.beforeClose"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      :title="editing ? '编辑政策解读' : '新增政策解读'"
      size="700px"
    >
      <el-form
        novalidate
        :disabled="saving"
        label-position="top"
        @submit.prevent="onSave"
      >
        <GroupedFields
          ref="editorFields"
          :model-value="form"
          :groups="editorGroups"
          :submit-error="saveError"
        />
      </el-form>
      <template #footer>
        <span
          v-if="editorGuard.dirty.value"
          class="editor-dirty"
          role="status"
        >有未保存的修改</span>
        <el-button
          :disabled="saving"
          @click="editorGuard.close"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="onSave"
        >
          保存
        </el-button>
      </template>
    </el-drawer>
  </div>
</template>
