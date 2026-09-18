<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createInterpretation,
  downloadPolicy,
  importInterpretations,
  interpretationOptions,
  listInterpretations,
  updateInterpretation,
  type InterpretationItem,
} from '@/api/policy'
import { errorMessage, isApiError } from '@/api/errors'
import { importUi, reportImportResult, runExcelImport } from '@/api/excelImport'
import FilterSelect from '@/components/FilterSelect.vue'
import ListPage from '@/components/ListPage.vue'
import ListEmpty from '@/components/ListEmpty.vue'
import GroupedFields, { type EditorGroup } from '@/components/GroupedFields.vue'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'

const auth = useAuthStore()
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
}

const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const items = ref<InterpretationItem[]>([])
const total = ref(0)
const query = reactive({
  policy_title: '',
  industry_scenario_code: '',
  industry_l1: '',
  opportunity_type: '',
  page: 1,
  page_size: 20,
})
const visible = ref(false)
const saving = ref(false)
const editing = ref<InterpretationItem | null>(null)
const form = reactive({ ...emptyForm })
const options = reactive({
  policy_title: [] as string[],
  industry_scenario_code: [] as string[],
  industry_l1: [] as string[],
  opportunity_type: [] as string[],
})

const tableColumns = [
  { prop: 'policy_uid', label: '政策唯一标识', minWidth: 200 },
  { prop: 'policy_title', label: '政策原文名称', minWidth: 220 },
  { prop: 'industry_scenario_code', label: '行业场景编码', minWidth: 180 },
  { prop: 'industry_code', label: '行业编码', width: 120 },
  { prop: 'industry_l1', label: '一级行业', width: 120 },
  { prop: 'industry_l2', label: '二级行业', width: 120 },
  { prop: 'industry_l3', label: '三级行业', width: 120 },
  { prop: 'scenario_code', label: '场景编码', width: 140 },
  { prop: 'scenario_l1_name', label: '一级场景名称', minWidth: 140 },
  { prop: 'scenario_l2_name', label: '二级场景名称', minWidth: 140 },
  { prop: 'scenario_l3_name', label: '三级场景名称', minWidth: 140 },
  { prop: 'target_customers', label: '目标客户当前政策影响客户群', minWidth: 220 },
  { prop: 'relation_key', label: '关联主键', minWidth: 200 },
  { prop: 'opportunity_type', label: '机会类型', width: 110 },
  { prop: 'policy_summary', label: '政策要文', minWidth: 220 },
  { prop: 'has_subsidy', label: '有无政府补贴', width: 120 },
  { prop: 'subsidy_content', label: '补贴内容', minWidth: 180 },
  { prop: 'market_opportunity', label: '政策市场机会', minWidth: 180 },
  { prop: 'info_level', label: '信息化等级', width: 110 },
  { prop: 'is_new_scenario', label: '是否新增场景', width: 120 },
  { prop: 'new_scenario_level', label: '新增场景级别', width: 120 },
  { prop: 'created_at', label: '入库时间', width: 170, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 170, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
] as const

function cellValue(row: InterpretationItem, prop: string): string {
  return String(row[prop as keyof InterpretationItem] ?? '')
}

async function loadOptions() {
  try {
    const data = await interpretationOptions()
    options.policy_title = (data.policy_title as string[]) ?? []
    options.industry_scenario_code = (data.industry_scenario_code as string[]) ?? []
    options.industry_l1 = (data.industry_l1 as string[]) ?? []
    options.opportunity_type = (data.opportunity_type as string[]) ?? []
  } catch {
    /* 选项失败不影响列表 */
  }
}

let loadSequence = 0

async function load() {
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  const filtered = Object.entries(query).some(([key, value]) =>
    !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
  try {
    const page = await listInterpretations({
      policy_title: query.policy_title || undefined,
      industry_scenario_code: query.industry_scenario_code || undefined,
      industry_l1: query.industry_l1 || undefined,
      opportunity_type: query.opportunity_type || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    if (sequence !== loadSequence) return
    items.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = errorMessage(error, '加载政策解读失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function onResetFilters() {
  query.policy_title = ''
  query.industry_scenario_code = ''
  query.industry_l1 = ''
  query.opportunity_type = ''
  onSearch()
}

function onSearch() {
  query.page = 1
  void load()
}

function openCreate() {
  editing.value = null
  Object.assign(form, emptyForm)
  visible.value = true
}

function openEdit(row: InterpretationItem) {
  editing.value = row
  Object.assign(form, emptyForm)
  for (const key of Object.keys(emptyForm) as (keyof typeof emptyForm)[]) {
    form[key] = String(row[key] ?? '')
  }
  visible.value = true
}

async function onSave() {
  if (saving.value) return
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
    await Promise.all([load(), loadOptions()])
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert('数据已被他人修改或关联主键重复，请重新加载。', '无法保存')
      await load()
    } else {
      ElMessage.error(errorMessage(error, '保存失败'))
    }
  } finally {
    saving.value = false
  }
}

async function onImport(file: File) {
  try {
    const result = await runExcelImport(file, (onProgress) => importInterpretations(file, onProgress))
    reportImportResult(result, '政策解读-跳过明细.xlsx')
    await Promise.all([load(), loadOptions()])
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

const exporting = ref(false)

async function onExport() {
  if (exporting.value) return
  exporting.value = true
  try {
    await downloadPolicy('/policy/interpretations/export', '政策解读表.xlsx')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'policy.interpretations' } })
}

onMounted(() => {
  void load()
  void loadOptions()
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
const editorGuard = useUnsavedForm(visible, () => form, saving)
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
            <el-button :disabled="importUi.visible">
              上传 Excel
            </el-button>
          </el-tooltip>
        </el-upload>
        <el-button
          :loading="exporting"
          @click="onExport"
        >
          下载 Excel
        </el-button>
        <el-button
          v-if="canAudit"
          @click="openLogs"
        >
          操作记录
        </el-button>
      </template>
      <template #filters>
        <el-form
          class="filter-form"
          inline
          label-position="top"
          @submit.prevent="onSearch"
        >
          <div class="filter-form__fields">
            <el-form-item label="政策原文名称">
              <FilterSelect
                v-model="query.policy_title"
                :options="options.policy_title"
              />
            </el-form-item>
            <el-form-item label="行业场景编码">
              <FilterSelect
                v-model="query.industry_scenario_code"
                :options="options.industry_scenario_code"
              />
            </el-form-item>
            <el-form-item label="一级行业">
              <FilterSelect
                v-model="query.industry_l1"
                :options="options.industry_l1"
                size="short"
              />
            </el-form-item>
            <el-form-item label="机会类型">
              <FilterSelect
                v-model="query.opportunity_type"
                :options="options.opportunity_type"
                size="short"
              />
            </el-form-item>
          </div>
          <el-form-item class="filter-form__submit">
            <el-button
              native-type="submit"
              type="primary"
            >
              查询
            </el-button>
            <el-button @click="onResetFilters">
              重置
            </el-button>
          </el-form-item>
        </el-form>
      </template>
      <el-table
        v-loading="loading"
        class="data-table"
        :data="items"
        stripe
        border
      >
        <template #empty>
          <ListEmpty
            :loading="loading"
            :filtered="resultFiltered"
            @reset="onResetFilters"
          />
        </template>
        <el-table-column
          v-for="col in tableColumns"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
          :width="'width' in col ? col.width : undefined"
          :min-width="'minWidth' in col ? col.minWidth : undefined"
          show-overflow-tooltip
        >
          <template
            v-if="'time' in col && col.time"
            #default="{ row }"
          >
            {{ formatTime(cellValue(row, col.prop)) }}
          </template>
        </el-table-column>
        <el-table-column
          v-if="canWrite"
          label="操作"
          width="80"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </ListPage>
    <el-drawer
      v-model="visible"
      class="editor-overlay"
      :before-close="editorGuard.beforeClose"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      :title="editing ? '编辑政策解读' : '新增政策解读'"
      size="700px"
    >
      <el-form
        :disabled="saving"
        label-position="top"
        @submit.prevent="onSave"
      >
        <GroupedFields
          :model-value="form"
          :groups="editorGroups"
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
