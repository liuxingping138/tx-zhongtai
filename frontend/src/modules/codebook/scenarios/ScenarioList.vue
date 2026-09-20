<script setup lang="ts">
import { Plus, Upload, Download, Clock } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createScenario,
  downloadCodebook,
  importScenarios,
  listScenarios,
  scenarioOptions,
  updateScenario,
  type ScenarioItem,
} from '@/api/codebook'
import { errorMessage, isApiError } from '@/api/errors'
import { importUi, reportImportResult, runExcelImport } from '@/api/excelImport'
import FilterSelect from '@/components/FilterSelect.vue'
import ListPage from '@/components/ListPage.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useListQuery } from '@/composables/useListQuery'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import GroupedFields, { type EditorGroup } from '@/components/GroupedFields.vue'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const canWrite = computed(() => auth.canFull('codebook.scenarios'))
const canAudit = computed(() => auth.canRead('system.audit'))

const fields: { key: keyof ScenarioItem; label: string }[] = [
  { key: 'industry_scenario_code', label: '行业场景编码' },
  { key: 'industry_code', label: '行业编码' },
  { key: 'industry_l1', label: '项目一级行业' },
  { key: 'industry_l2', label: '项目二级行业' },
  { key: 'industry_l3', label: '项目三级行业' },
  { key: 'scenario_tag', label: '场景标签' },
  { key: 'scenario_level', label: '场景level' },
  { key: 'scenario_type', label: '场景类型' },
  { key: 'desc_90', label: '场景描述(90字)' },
  { key: 'desc_130', label: '场景描述(130字)' },
  { key: 'desc_pest', label: '场景描述(PEST总结)' },
  { key: 'scenario_source', label: '场景来源' },
  { key: 'scenario_hierarchy', label: '场景层级' },
  { key: 'scenario_code', label: '场景编码' },
  { key: 'scenario_l1_name', label: '项目一级场景名称' },
  { key: 'scenario_l1_desc', label: '项目一级场景描述' },
  { key: 'scenario_l2_name', label: '项目二级场景名称' },
  { key: 'scenario_l2_desc', label: '项目二级场景描述' },
  { key: 'scenario_l3_name', label: '项目三级场景名称' },
  { key: 'scenario_l3_desc', label: '项目三级场景描述' },
  { key: 'customer_group_name', label: '客群名称' },
  { key: 'customer_group_industry', label: '客群行业' },
  { key: 'org_keywords', label: '机构及企业名称包含关键词' },
  { key: 'scope_keywords', label: '经营范围包含' },
  { key: 'customer_level', label: '客户等级' },
  { key: 'customer_category', label: '客户类别' },
  { key: 'product_l1_name', label: '项目一级产品名称' },
  { key: 'product_l2_name', label: '项目二级产品名称' },
  { key: 'branch_count', label: '下属分支机构数' },
  { key: 'product_l1_sort', label: '一级产品排序（正序）' },
  { key: 'product_l2_sort', label: '二级产品排序（正序）' },
]

const longFields = new Set([
  'desc_90',
  'desc_130',
  'desc_pest',
  'scenario_l1_desc',
  'scenario_l2_desc',
  'scenario_l3_desc',
  'org_keywords',
  'scope_keywords',
])

const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const items = ref<ScenarioItem[]>([])
const total = ref(0)
const query = reactive({
  industry_scenario_code: '',
  industry_l1: '',
  scenario_tag: '',
  customer_group_name: '',
  page: 1,
  page_size: 20,
})
const visible = ref(false)
const saving = ref(false)
const saveError = ref('')
const editing = ref<ScenarioItem | null>(null)
const form = reactive<Record<string, string>>({})
const options = reactive({
  industry_scenario_code: [] as string[],
  industry_l1: [] as string[],
  scenario_tag: [] as string[],
  customer_group_name: [] as string[],
})

const columnLabels: Record<string, string> = {
  industry_l1: '一级行业',
  industry_l2: '二级行业',
  industry_l3: '三级行业',
  scenario_l1_name: '一级场景',
  scenario_l2_name: '二级场景',
  scenario_l3_name: '三级场景',
  scenario_l1_desc: '一级场景描述',
  scenario_l2_desc: '二级场景描述',
  scenario_l3_desc: '三级场景描述',
  org_keywords: '机构名称关键词',
  product_l1_name: '一级产品',
  product_l2_name: '二级产品',
  branch_count: '分支机构数',
  product_l1_sort: '一级产品排序',
  product_l2_sort: '二级产品排序',
}

const tableColumns = [
  ...fields.map((field) => ({
    prop: field.key,
    label: columnLabels[field.key] || field.label,
    fullLabel: field.label,
    ...(longFields.has(field.key) ? { width: 300, wrap: true }
      : field.key === 'industry_scenario_code' ? { width: 220 }
      : field.key === 'scenario_tag' ? { minWidth: 220, grow: 1 }
      : field.key === 'customer_group_name' ? { minWidth: 230, grow: 2 }
      : field.key === 'product_l1_name' ? { minWidth: 180, grow: 1 }
      : { width: 160 }),
  })),
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
]


async function loadOptions() {
  try {
    const data = await scenarioOptions()
    options.industry_scenario_code = data.industry_scenario_code ?? []
    options.industry_l1 = data.industry_l1 ?? []
    options.scenario_tag = data.scenario_tag ?? []
    options.customer_group_name = data.customer_group_name ?? []
  } catch {
    /* 选项失败不影响列表 */
  }
}

const listQuery = useListQuery(query, load)

let loadSequence = 0

async function load() {
  void listQuery.commit()
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  const filtered = Object.entries(query).some(([key, value]) =>
    !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
  try {
    const page = await listScenarios({
      industry_scenario_code: query.industry_scenario_code || undefined,
      industry_l1: query.industry_l1 || undefined,
      scenario_tag: query.scenario_tag || undefined,
      customer_group_name: query.customer_group_name || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    if (sequence !== loadSequence) return
    items.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = errorMessage(error, '加载行业场景码表失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function onResetFilters() {
  query.industry_scenario_code = ''
  query.industry_l1 = ''
  query.scenario_tag = ''
  query.customer_group_name = ''
  onSearch()
}

function onSearch() {
  query.page = 1
  void load()
}

function openCreate() {
  saveError.value = ''
  editing.value = null
  for (const field of fields) {
    form[field.key] = ''
  }
  visible.value = true
}

function openEdit(row: ScenarioItem) {
  saveError.value = ''
  editing.value = row
  for (const field of fields) {
    form[field.key] = String(row[field.key] ?? '')
  }
  visible.value = true
}

async function onSave() {
  if (saving.value) return
  saveError.value = ''
  if (!await editorFields.value?.validate()) return
  saving.value = true
  try {
    if (editing.value) {
      await updateScenario(editing.value.id, { ...form, version: editing.value.version })
    } else {
      await createScenario({ ...form })
    }
    ElMessage.success('已保存')
    visible.value = false
    await Promise.all([load(), loadOptions()])
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert(
        editing.value ? '数据已被他人修改，请重新加载后再编辑。' : '已存在完全相同的场景记录。',
        '无法保存',
      )
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
    const result = await runExcelImport(file, (onProgress) => importScenarios(file, onProgress))
    reportImportResult(result, '行业场景-跳过明细.xlsx')
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
    await downloadCodebook('/codebook/scenarios/export', '行业场景字典表.xlsx')
    ElMessage.success('下载已开始，请查看浏览器下载列表')
  } catch {
    ElMessage.error('下载失败，请重试')
  } finally {
    exporting.value = false
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'codebook.scenarios' } })
}

onMounted(() => {
  void load()
  void loadOptions()
})

const editorGroups: EditorGroup[] = [
  {
    "title": "行业与场景标识",
    "hint": "编码用于关联业务数据，请与现有码表保持一致。",
    "fields": [
      {
        "key": "industry_scenario_code",
        "label": "行业场景编码",
        "long": false,
        "required": false,
        "maxLength": 64
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
        "label": "项目一级行业",
        "long": false,
        "required": false,
        "maxLength": 128
      },
      {
        "key": "industry_l2",
        "label": "项目二级行业",
        "long": false,
        "required": false,
        "maxLength": 128
      },
      {
        "key": "industry_l3",
        "label": "项目三级行业",
        "long": false,
        "required": false,
        "maxLength": 128
      },
      {
        "key": "scenario_tag",
        "label": "场景标签",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "scenario_level",
        "label": "场景level",
        "long": false,
        "required": false,
        "maxLength": 16
      },
      {
        "key": "scenario_type",
        "label": "场景类型",
        "long": false,
        "required": false,
        "maxLength": 16
      },
      {
        "key": "scenario_source",
        "label": "场景来源",
        "long": false,
        "required": false
      },
      {
        "key": "scenario_hierarchy",
        "label": "场景层级",
        "long": false,
        "required": false,
        "maxLength": 64
      },
      {
        "key": "scenario_code",
        "label": "场景编码",
        "long": false,
        "required": false,
        "maxLength": 64
      }
    ]
  },
  {
    "title": "场景描述",
    "hint": "分别填写不同用途的场景摘要和层级说明。",
    "fields": [
      {
        "key": "desc_90",
        "label": "场景描述(90字)",
        "long": true,
        "required": false
      },
      {
        "key": "desc_130",
        "label": "场景描述(130字)",
        "long": true,
        "required": false
      },
      {
        "key": "desc_pest",
        "label": "场景描述(PEST总结)",
        "long": true,
        "required": false
      },
      {
        "key": "scenario_l1_name",
        "label": "项目一级场景名称",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "scenario_l1_desc",
        "label": "项目一级场景描述",
        "long": true,
        "required": false
      },
      {
        "key": "scenario_l2_name",
        "label": "项目二级场景名称",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "scenario_l2_desc",
        "label": "项目二级场景描述",
        "long": true,
        "required": false
      },
      {
        "key": "scenario_l3_name",
        "label": "项目三级场景名称",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "scenario_l3_desc",
        "label": "项目三级场景描述",
        "long": true,
        "required": false
      }
    ]
  },
  {
    "title": "目标客群",
    "hint": "描述适用客群及筛选线索。",
    "fields": [
      {
        "key": "customer_group_name",
        "label": "客群名称",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "customer_group_industry",
        "label": "客群行业",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "org_keywords",
        "label": "机构及企业名称包含关键词",
        "long": true,
        "required": false
      },
      {
        "key": "scope_keywords",
        "label": "经营范围包含",
        "long": true,
        "required": false
      },
      {
        "key": "customer_level",
        "label": "客户等级",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "customer_category",
        "label": "客户类别",
        "long": false,
        "required": false,
        "maxLength": 255
      }
    ]
  },
  {
    "title": "产品与排序",
    "hint": "补充产品名称及展示顺序，排序按正序填写。",
    "fields": [
      {
        "key": "product_l1_name",
        "label": "项目一级产品名称",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "product_l2_name",
        "label": "项目二级产品名称",
        "long": false,
        "required": false,
        "maxLength": 255
      },
      {
        "key": "branch_count",
        "label": "下属分支机构数",
        "long": false,
        "required": false,
        "maxLength": 64
      },
      {
        "key": "product_l1_sort",
        "label": "一级产品排序（正序）",
        "long": false,
        "required": false,
        "maxLength": 32
      },
      {
        "key": "product_l2_sort",
        "label": "二级产品排序（正序）",
        "long": false,
        "required": false,
        "maxLength": 32
      }
    ]
  }
]
const editorFields = ref<InstanceType<typeof GroupedFields>>()
const editorGuard = useUnsavedForm(visible, () => form, saving)

const legacyDefaults = ['scenario_tag', 'industry_l1', 'customer_group_name', 'product_l1_name']

const detailColumns = computed(() => {
  const known = new Set(tableColumns.map(col => String(col.prop)))
  return [...tableColumns, ...editorGroups.flatMap(group => group.fields).filter(field => !known.has(field.key)).map(field => ({ prop: field.key, label: field.label }))]
})
const defaultColumns = computed(() => detailColumns.value.map(col => col.prop))
const selectedColumns = ref([...defaultColumns.value])
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
            content="按整行内容去重，重复记录会跳过；导入完成后可查看结果和校验报告。"
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
        <el-button
          :icon="Download"
          :loading="exporting"
          @click="onExport"
        >
          下载 Excel
        </el-button>
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
          @search="onSearch"
          @reset="onResetFilters"
        >
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
          <el-form-item label="场景标签">
            <FilterSelect
              v-model="query.scenario_tag"
              :options="options.scenario_tag"
            />
          </el-form-item>
          <template #advanced>
            <el-form-item label="客群名称">
              <FilterSelect
                v-model="query.customer_group_name"
                :options="options.customer_group_name"
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
        title-key="scenario_tag"
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
      :title="editing ? '编辑行业场景码表' : '新增行业场景码表'"
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
