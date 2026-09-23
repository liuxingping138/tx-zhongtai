<script setup lang="ts">
import { Plus, Upload, Download, Clock } from '@element-plus/icons-vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { importAfterAreaResolve } from '@/api/codebook'
import {
  clearSources,
  createSource,
  importSources,
  listSources,
  updateSource,
  type SourceItem,
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
/** 导出单独一档：只读角色能看不能导，按钮保留但禁用并说明原因。 */
const canExport = computed(() => auth.canExport('policy.sources'))
const router = useRouter()
const canWrite = computed(() => auth.canFull('policy.sources'))
const canPurge = computed(() => auth.canFull('policy.sources') && auth.isSuperadmin)
const canAudit = computed(() => auth.canRead('system.audit'))
const clearing = ref(false)

const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const items = ref<SourceItem[]>([])
const total = ref(0)
const query = reactive({
  site_name: [] as string[],
  province_name: [] as string[],
  city_name: [] as string[],
  tag: [] as string[],
  crawl_priority: [] as string[],
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/policy/sources')
const visible = ref(false)
const saving = ref(false)
const saveError = ref('')
const editing = ref<SourceItem | null>(null)
const emptyForm = {
  province_name: '',
  province_code: '',
  city_name: '',
  city_code: '',
  district_name: '',
  district_code: '',
  site_name: '',
  crawl_priority: '',
  url: '',
  tag: '',
  data_type: '',
  department: '',
}
const form = reactive({ ...emptyForm })

const tableColumns = [
  { prop: 'site_name', label: '网站名称', minWidth: 240, grow: 2 },
  { prop: 'province_name', label: '省份', width: 100 },
  { prop: 'city_name', label: '地市', width: 110 },
  { prop: 'district_name', label: '区县', width: 120 },
  { prop: 'crawl_priority', label: '抓取优先级', fullLabel: '网站梳理和抓取的优先级', width: 120 },
  { prop: 'url', label: '链接', minWidth: 240, link: true },
  { prop: 'tag', label: '标签', minWidth: 200, grow: 1 },
  { prop: 'data_type', label: '数据类型', fullLabel: '数据类型（综合-0、政策-1、新闻-2）注：0和1链接下全爬，2爬聚集板块', width: 120 },
  { prop: 'department', label: '所属部门', width: 220 },
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 190, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
] as const

const cityBinding = computed(() => filters.bindCity('city_name', query.province_name))




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
    const page = await listSources({
      site_name: query.site_name || undefined,
      province_name: query.province_name || undefined,
      city_name: query.city_name || undefined,
      tag: query.tag || undefined,
      crawl_priority: query.crawl_priority || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    if (sequence !== loadSequence) return
    items.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = errorMessage(error, '加载信源失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function onResetFilters() {
  query.site_name = []
  query.province_name = []
  query.city_name = []
  query.tag = []
  query.crawl_priority = []
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

function payloadFromForm() {
  return Object.fromEntries(Object.keys(emptyForm).map((key) => [key, form[key as keyof typeof form]]))
}

function openEdit(row: SourceItem) {
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
  if (!form.site_name.trim()) {
    ElMessage.warning('请填写网站名称')
    return
  }
  if (!form.province_code.trim() && !form.city_code.trim() && !form.district_code.trim()) {
    await editorFields.value?.setError('province_code', '请至少填写省份、地市或区县编码中的一项')
    return
  }
  saving.value = true
  try {
    const payload = payloadFromForm()
    if (editing.value) {
      await updateSource(editing.value.id, { ...payload, version: editing.value.version })
    } else {
      await createSource(payload)
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
      importAfterAreaResolve(file, importSources, onProgress),
    )
    reportImportResult(result, '信源管理-上传校验.xlsx')
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
    await downloadFile('/policy/sources/export', '信源管理.xlsx', filtersForExport(listQuery.applied))
    ElMessage.success('下载已开始，请查看浏览器下载列表')
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败，请重试'))
  } finally {
    exporting.value = false
  }
}

async function onClear() {
  try {
    await ElMessageBox.confirm(
      '将删除信源管理中的全部数据，且无法恢复。确定清空？',
      '清空信源表',
      {
        type: 'warning',
        confirmButtonText: '确认清空',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  clearing.value = true
  try {
    const result = await clearSources()
    ElMessage.success(`已清空 ${result.deleted} 条`)
    query.page = 1
    await Promise.all([load(), filters.load()])
  } catch (error) {
    ElMessage.error(errorMessage(error, '清空失败'))
  } finally {
    clearing.value = false
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'policy.sources' } })
}

onMounted(() => {
  void load()
  void filters.load()
})

const editorGroups: EditorGroup[] = [
  {
    "title": "基础信息",
    "hint": "填写信源网站与所属部门，便于识别和维护。",
    "fields": [
      {
        "key": "site_name",
        "label": "网站名称",
        "required": true,
        "maxLength": 255
      },
      {
        "key": "department",
        "label": "所属部门",
        "maxLength": 255
      },
      {
        "key": "url",
        "label": "网站链接",
        "long": true,
        "placeholder": "https://",
        "hint": "建议填写完整的网址，便于直接访问。"
      }
    ]
  },
  {
    "title": "所属地区",
    "hint": "省、市、区县编码至少填写一项；名称与编码请保持对应。",
    "fields": [
      {
        "key": "province_name",
        "label": "省份名称",
        "maxLength": 64
      },
      {
        "key": "province_code",
        "label": "省份编码",
        "placeholder": "如：11",
        "maxLength": 8
      },
      {
        "key": "city_name",
        "label": "地市名称",
        "maxLength": 64
      },
      {
        "key": "city_code",
        "label": "地市编码",
        "placeholder": "如：1101",
        "maxLength": 8
      },
      {
        "key": "district_name",
        "label": "区县名称",
        "maxLength": 64
      },
      {
        "key": "district_code",
        "label": "区县编码",
        "placeholder": "如：110101",
        "maxLength": 8
      }
    ]
  },
  {
    "title": "采集与标签",
    "hint": "按业务约定填写采集优先级及分类。",
    "fields": [
      {
        "key": "crawl_priority",
        "label": "采集优先级",
        "maxLength": 255
      },
      {
        "key": "tag",
        "label": "标签"
      },
      {
        "key": "data_type",
        "label": "数据类型",
        "hint": "综合填 0，政策填 1，新闻填 2；0、1 全爬，2 爬聚集板块。"
      }
    ]
  }
]
const editorFields = ref<InstanceType<typeof GroupedFields>>()
const editorGuard = useUnsavedForm(visible, () => form, saving)

const legacyDefaults = ['site_name', 'province_name', 'city_name', 'tag', 'crawl_priority']

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
      title="信源管理"
      hint="维护政策采集网站、所属地区与采集规则。"
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
            content="上传后自动补齐地区编码；存在重复或地区编码缺失时整批退回，并下载校验报告。"
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
          v-if="canPurge"
          type="danger"
          plain
          :loading="clearing"
          @click="onClear"
        >
          清空表
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
          :applied="listQuery.applied"
          @search="onSearch"
          @reset="onResetFilters"
        >
          <el-form-item label="网站名称">
            <FilterSelect
              v-model="query.site_name"
              v-bind="filters.bind('site_name')"
            />
          </el-form-item>
          <el-form-item label="省份">
            <FilterSelect
              v-model="query.province_name"
              v-bind="filters.bind('province_name')"
              size="short"
            />
          </el-form-item>
          <el-form-item label="地市">
            <FilterSelect
              v-model="query.city_name"
              v-bind="cityBinding"
              size="short"
            />
          </el-form-item>
          <template #advanced>
            <el-form-item label="标签">
              <FilterSelect
                v-model="query.tag"
                v-bind="filters.bind('tag')"
              />
            </el-form-item>
            <el-form-item label="网站优先级">
              <FilterSelect
                v-model="query.crawl_priority"
                v-bind="filters.bind('crawl_priority')"
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
        title-key="site_name"
        detail-title="信源详情"
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
      :title="editing ? '编辑信源' : '新增信源'"
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
