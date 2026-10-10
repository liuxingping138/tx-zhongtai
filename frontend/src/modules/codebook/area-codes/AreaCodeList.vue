<script setup lang="ts">
import { Plus, Upload, Download, Clock } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createAreaCode,
  importAreaCodes,
  listAreaCodes,
  updateAreaCode,
  type AreaCodeItem,
} from '@/api/codebook'
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
const canExport = computed(() => auth.canExport('codebook.area_codes'))
const router = useRouter()
const canWrite = computed(() => auth.canFull('codebook.area_codes'))
const canAudit = computed(() => auth.canRead('system.audit'))

const fields: { key: keyof AreaCodeItem; label: string; required?: boolean }[] = [
  { key: 'prov_id', label: '省份编码' },
  { key: 'prov_name', label: '省份名称' },
  { key: 'city_id', label: '城市编码' },
  { key: 'city_name', label: '城市名称' },
  { key: 'county_id', label: '区县编码', required: true },
  { key: 'county_name', label: '区县名称' },
  { key: 'alias_prov_name', label: '省份别名' },
  { key: 'alias_city_name', label: '城市别名' },
  { key: 'alias_county_name', label: '区县别名' },
  { key: 'city_name_short', label: '城市简称' },
  { key: 'county_name_short', label: '区县简称' },
]

const query = reactive({
  prov_name: [] as string[],
  city_name: [] as string[],
  county_name: [] as string[],
  page: 1,
  page_size: 20,
})
const visible = ref(false)
const saving = ref(false)
const saveError = ref('')
const editing = ref<AreaCodeItem | null>(null)
const form = reactive<Record<string, string>>({})
const filters = useFilterOptions('/codebook/area-codes')

const tableColumns = [
  ...fields.map((field) => ({
    prop: field.key,
    label: field.label,
    ...(field.key.endsWith('_id') ? { width: 112 } : { width: 160 }),
  })),
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
]



const listQuery = useListQuery(query, (): Promise<void> => load())

const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: (params) => listAreaCodes({
      prov_name: params.prov_name || undefined,
      city_name: params.city_name || undefined,
      county_name: params.county_name || undefined,
      page: params.page,
      page_size: params.page_size,
  }),
  errorText: '加载省市区编码表失败',
})

function onResetFilters() {
  query.prov_name = []
  query.city_name = []
  query.county_name = []
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
  for (const field of fields) {
    form[field.key] = ''
  }
  visible.value = true
}

function openEdit(row: AreaCodeItem) {
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
  if (!form.county_id?.trim()) {
    ElMessage.warning('区县编码不能为空')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await updateAreaCode(editing.value.id, { ...form, version: editing.value.version })
    } else {
      await createAreaCode({ ...form })
    }
    ElMessage.success('已保存')
    visible.value = false
    await Promise.all([load(), filters.load()])
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert(
        editing.value ? '数据已被他人修改，或区县编码已存在。' : '区县编码已存在。',
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
    const result = await runExcelImport(file, (onProgress) => importAreaCodes(file, onProgress))
    reportImportResult(result, '省市区编码-跳过明细.xlsx')
    await Promise.all([load(), filters.load()])
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

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'codebook.area_codes' } })
}

onMounted(() => {
  void load()
  void filters.load()
})

const editorGroups: EditorGroup[] = [
  {
    "title": "行政区划",
    "hint": "区县编码为必填项，请保留原始编码格式。",
    "fields": [
      {
        "key": "prov_id",
        "label": "省份编码",
        "long": false,
        "required": false,
        "maxLength": 64
      },
      {
        "key": "prov_name",
        "label": "省份名称",
        "long": false,
        "required": false,
        "maxLength": 200
      },
      {
        "key": "city_id",
        "label": "城市编码",
        "long": false,
        "required": false,
        "maxLength": 64
      },
      {
        "key": "city_name",
        "label": "城市名称",
        "long": false,
        "required": false,
        "maxLength": 200
      },
      {
        "key": "county_id",
        "label": "区县编码",
        "long": false,
        "required": true,
        "maxLength": 64
      },
      {
        "key": "county_name",
        "label": "区县名称",
        "long": false,
        "required": false,
        "maxLength": 200
      }
    ]
  },
  {
    "title": "别名与简称",
    "hint": "用于识别不同名称写法，无对应内容可留空。",
    "fields": [
      {
        "key": "alias_prov_name",
        "label": "省份别名",
        "long": false,
        "required": false,
        "maxLength": 200
      },
      {
        "key": "alias_city_name",
        "label": "城市别名",
        "long": false,
        "required": false,
        "maxLength": 200
      },
      {
        "key": "alias_county_name",
        "label": "区县别名",
        "long": false,
        "required": false,
        "maxLength": 200
      },
      {
        "key": "city_name_short",
        "label": "城市简称",
        "long": false,
        "required": false,
        "maxLength": 200
      },
      {
        "key": "county_name_short",
        "label": "区县简称",
        "long": false,
        "required": false,
        "maxLength": 200
      }
    ]
  }
]
const editorFields = ref<InstanceType<typeof GroupedFields>>()
const editorGuard = useUnsavedForm(visible, () => form, saving)

const legacyDefaults = ['county_name', 'prov_name', 'city_name', 'county_id']

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
            content="按区县编码去重，已有编码会跳过；校验报告列出需处理的记录。"
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
        title-key="county_name"
        detail-title="省市区详情"
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
      :title="editing ? '编辑省市区编码' : '新增省市区编码'"
      size="560px"
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
