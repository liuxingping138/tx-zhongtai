<script setup lang="ts">
import { Plus, Upload, Download, Clock } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { importAfterAreaResolve } from '@/api/codebook'
import {
  createBaseTag,
  importBaseTags,
  listBaseTags,
  updateBaseTag,
  type BaseTagItem,
} from '@/api/policy'
import { downloadFile } from '@/api/download'
import { errorMessage, isApiError } from '@/api/errors'
import { importUi, reportImportResult, runExcelImport } from '@/api/excelImport'
import FilterSelect from '@/components/FilterSelect.vue'
import ListPage from '@/components/ListPage.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { filtersForExport, useListQuery } from '@/composables/useListQuery'
import BusinessTable from '@/components/BusinessTable.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import GroupedFields, { type EditorGroup } from '@/components/GroupedFields.vue'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const canWrite = computed(() => auth.canFull('policy.base_tags'))
const canAudit = computed(() => auth.canRead('system.audit'))

const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const items = ref<BaseTagItem[]>([])
const total = ref(0)
const query = reactive({
  policy_name: '',
  province_name: '',
  policy_types: '',
  is_penetrate: '',
  need_interpret: '',
  page: 1,
  page_size: 20,
})
const visible = ref(false)
const saving = ref(false)
const saveError = ref('')
const editing = ref<BaseTagItem | null>(null)
const emptyForm = {
  policy_name: '',
  issuing_dept: '',
  issuer_industry: '',
  policy_level: '',
  province_code: '',
  province_name: '',
  city_code: '',
  city_name: '',
  issued_at: '',
  policy_types: '',
  source_url: '',
  is_penetrate: '',
  penetrate_words: '',
  penetrate_score: '',
  need_interpret: '',
  remark: '',
}
const form = reactive({ ...emptyForm })
const filters = useFilterOptions('/policy/base-tags')

const tableColumns = [
  { prop: 'policy_name', label: '政策名称', minWidth: 320, grow: 2 },
  { prop: 'issuing_dept', label: '出台部门', width: 220 },
  { prop: 'issuer_industry', label: '发文机构行业', minWidth: 140 },
  { prop: 'policy_level', label: '政策层级', width: 110 },
  { prop: 'province_code', label: '省份编码', width: 100 },
  { prop: 'province_name', label: '省份名称', width: 110 },
  { prop: 'city_code', label: '地市编码', width: 100 },
  { prop: 'city_name', label: '地市名称', width: 110 },
  { prop: 'issued_at', label: '出台日期', fullLabel: '当前政策出台时间', width: 140 },
  { prop: 'policy_types', label: '政策类型', minWidth: 200, grow: 1, wrap: true },
  { prop: 'source_url', label: '原始网站链接', minWidth: 240, link: true },
  { prop: 'is_penetrate', label: '是否穿透', width: 100 },
  { prop: 'penetrate_words', label: '穿透词', minWidth: 180 },
  { prop: 'penetrate_score', label: '穿透词评分', width: 110 },
  { prop: 'need_interpret', label: '是否解读', width: 100 },
  { prop: 'remark', label: '备注', minWidth: 160 },
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
] as const




const listQuery = useListQuery(query, load)

let loadSequence = 0

async function load() {
  void listQuery.commit()
  listQuery.captureApplied()
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  const filtered = Object.entries(query).some(([key, value]) =>
    !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
  try {
    const page = await listBaseTags({
      policy_name: query.policy_name || undefined,
      province_name: query.province_name || undefined,
      policy_types: query.policy_types || undefined,
      is_penetrate: query.is_penetrate || undefined,
      need_interpret: query.need_interpret || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    if (sequence !== loadSequence) return
    items.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = errorMessage(error, '加载政策基础标签失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function onResetFilters() {
  query.policy_name = ''
  query.province_name = ''
  query.policy_types = ''
  query.is_penetrate = ''
  query.need_interpret = ''
  onSearch()
}

function onSearch() {
  query.page = 1
  void load()
}

function openCreate() {
  saveError.value = ''
  editing.value = null
  Object.assign(form, emptyForm)
  visible.value = true
}

function openEdit(row: BaseTagItem) {
  saveError.value = ''
  editing.value = row
  Object.assign(form, emptyForm)
  for (const key of Object.keys(emptyForm) as (keyof typeof emptyForm)[]) {
    form[key] = String(row[key] ?? '')
  }
  visible.value = true
}

async function onSave() {
  if (saving.value) return
  saveError.value = ''
  if (!await editorFields.value?.validate()) return
  if (!form.policy_name.trim()) {
    ElMessage.warning('请填写政策名称')
    return
  }
  saving.value = true
  try {
    const payload = Object.fromEntries(
      Object.keys(emptyForm).map((key) => [key, form[key as keyof typeof form]]),
    )
    if (editing.value) {
      await updateBaseTag(editing.value.id, { ...payload, version: editing.value.version })
    } else {
      await createBaseTag(payload)
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
    const result = await runExcelImport(file, (onProgress) =>
      importAfterAreaResolve(file, importBaseTags, onProgress),
    )
    reportImportResult(result, '政策基础标签-上传校验.xlsx')
    if (!result.rejected) {
      await Promise.all([load(), filters.load()])
    }
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
    await downloadFile('/policy/base-tags/export', '政策基础标签表.xlsx', filtersForExport(listQuery.applied))
    ElMessage.success('下载已开始，请查看浏览器下载列表')
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败，请重试'))
  } finally {
    exporting.value = false
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'policy.base_tags' } })
}

onMounted(() => {
  void load()
  void filters.load()
})

const editorGroups: EditorGroup[] = [
  {
    "title": "政策基础信息",
    "hint": "政策名称为必填项，其余信息按原文填写。",
    "fields": [
      {
        "key": "policy_name",
        "label": "政策名称",
        "required": true,
        "long": true
      },
      {
        "key": "issuing_dept",
        "label": "出台部门",
        "maxLength": 255
      },
      {
        "key": "issuer_industry",
        "label": "发文机构行业",
        "maxLength": 255
      },
      {
        "key": "policy_level",
        "label": "政策层级",
        "maxLength": 64
      },
      {
        "key": "issued_at",
        "label": "出台时间",
        "placeholder": "如：2026-09-18",
        "maxLength": 64
      },
      {
        "key": "source_url",
        "label": "原始网站链接",
        "long": true,
        "placeholder": "https://"
      }
    ]
  },
  {
    "title": "所属地区",
    "hint": "地区名称和编码应与省市区码表保持一致。",
    "fields": [
      {
        "key": "province_name",
        "label": "省份名称",
        "maxLength": 64
      },
      {
        "key": "province_code",
        "label": "省份编码",
        "maxLength": 16
      },
      {
        "key": "city_name",
        "label": "地市名称",
        "maxLength": 64
      },
      {
        "key": "city_code",
        "label": "地市编码",
        "maxLength": 16
      }
    ]
  },
  {
    "title": "业务标签",
    "hint": "填写政策分类、穿透和解读信息，便于后续筛选。",
    "fields": [
      {
        "key": "policy_types",
        "label": "政策类型"
      },
      {
        "key": "is_penetrate",
        "label": "是否穿透",
        "maxLength": 32
      },
      {
        "key": "need_interpret",
        "label": "是否解读",
        "maxLength": 64
      },
      {
        "key": "penetrate_score",
        "label": "穿透词评分",
        "maxLength": 64
      },
      {
        "key": "penetrate_words",
        "label": "穿透词",
        "long": true
      },
      {
        "key": "remark",
        "label": "备注",
        "long": true
      }
    ]
  }
]
const editorFields = ref<InstanceType<typeof GroupedFields>>()
const editorGuard = useUnsavedForm(visible, () => form, saving)

const legacyDefaults = ['policy_name', 'province_name', 'policy_types', 'issued_at', 'need_interpret']

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
            content="上传后关联省市区编码，任一条记录关联失败则整批退回，详情见校验报告。"
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
          content="按当前已生效的筛选条件导出；未筛选时导出全表。"
          placement="bottom"
        >
          <el-button
            :icon="Download"
            :loading="exporting"
            @click="onExport"
          >
            下载 Excel
          </el-button>
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
          <el-form-item label="政策名称">
            <FilterSelect
              v-model="query.policy_name"
              v-bind="filters.bind('policy_name')"
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
        title-key="policy_name"
        detail-title="政策基础标签详情"
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
      :title="editing ? '编辑政策基础标签' : '新增政策基础标签'"
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

<style scoped>
.source-link {
  color: var(--zt-blue-600);
  text-decoration: none;
}

.source-link:hover {
  text-decoration: underline;
}
</style>
