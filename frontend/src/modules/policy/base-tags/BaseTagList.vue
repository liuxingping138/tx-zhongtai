<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { importAfterAreaResolve } from '@/api/codebook'
import {
  baseTagOptions,
  createBaseTag,
  downloadPolicy,
  importBaseTags,
  listBaseTags,
  updateBaseTag,
  type BaseTagItem,
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
const options = reactive({
  policy_name: [] as string[],
  province_name: [] as string[],
  policy_types: [] as string[],
  is_penetrate: [] as string[],
  need_interpret: [] as string[],
})

const tableColumns = [
  { prop: 'policy_name', label: '政策名称', minWidth: 220 },
  { prop: 'issuing_dept', label: '出台部门', minWidth: 160 },
  { prop: 'issuer_industry', label: '发文机构行业', minWidth: 140 },
  { prop: 'policy_level', label: '政策层级', width: 110 },
  { prop: 'province_code', label: '省份编码', width: 100 },
  { prop: 'province_name', label: '省份名称', width: 110 },
  { prop: 'city_code', label: '地市编码', width: 100 },
  { prop: 'city_name', label: '地市名称', width: 110 },
  { prop: 'issued_at', label: '当前政策出台时间', width: 160 },
  { prop: 'policy_types', label: '政策类型', minWidth: 160 },
  { prop: 'source_url', label: '原始网站链接', minWidth: 240, link: true },
  { prop: 'is_penetrate', label: '是否穿透', width: 100 },
  { prop: 'penetrate_words', label: '穿透词', minWidth: 180 },
  { prop: 'penetrate_score', label: '穿透词评分', width: 110 },
  { prop: 'need_interpret', label: '是否解读', width: 100 },
  { prop: 'remark', label: '备注', minWidth: 160 },
  { prop: 'created_at', label: '入库时间', width: 170, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 170, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
] as const

function cellValue(row: BaseTagItem, prop: string): string {
  return String(row[prop as keyof BaseTagItem] ?? '')
}

function hrefOf(url: string): string {
  const value = url.trim()
  if (!value) {
    return ''
  }
  if (/^https?:\/\//i.test(value)) {
    return value
  }
  return `https://${value}`
}

async function loadOptions() {
  try {
    const data = await baseTagOptions()
    options.policy_name = (data.policy_name as string[]) ?? []
    options.province_name = (data.province_name as string[]) ?? []
    options.policy_types = (data.policy_types as string[]) ?? []
    options.is_penetrate = (data.is_penetrate as string[]) ?? []
    options.need_interpret = (data.need_interpret as string[]) ?? []
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
  editing.value = null
  Object.assign(form, emptyForm)
  visible.value = true
}

function openEdit(row: BaseTagItem) {
  editing.value = row
  Object.assign(form, emptyForm)
  for (const key of Object.keys(emptyForm) as (keyof typeof emptyForm)[]) {
    form[key] = String(row[key] ?? '')
  }
  visible.value = true
}

async function onSave() {
  if (saving.value) return
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
    await Promise.all([load(), loadOptions()])
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert('数据已被他人修改或内容重复，请重新加载。', '无法保存')
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
    const result = await runExcelImport(file, (onProgress) =>
      importAfterAreaResolve(file, importBaseTags, onProgress),
    )
    reportImportResult(result, '政策基础标签-上传校验.xlsx')
    if (!result.rejected) {
      await Promise.all([load(), loadOptions()])
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
    await downloadPolicy('/policy/base-tags/export', '政策基础标签表.xlsx')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'policy.base_tags' } })
}

onMounted(() => {
  void load()
  void loadOptions()
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
const editorGuard = useUnsavedForm(visible, () => form, saving)
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
            <el-form-item label="政策名称">
              <FilterSelect
                v-model="query.policy_name"
                :options="options.policy_name"
              />
            </el-form-item>
            <el-form-item label="省份">
              <FilterSelect
                v-model="query.province_name"
                :options="options.province_name"
                size="short"
              />
            </el-form-item>
            <el-form-item label="政策类型">
              <FilterSelect
                v-model="query.policy_types"
                :options="options.policy_types"
              />
            </el-form-item>
            <el-form-item label="是否穿透">
              <FilterSelect
                v-model="query.is_penetrate"
                :options="options.is_penetrate"
                size="short"
              />
            </el-form-item>
            <el-form-item label="是否解读">
              <FilterSelect
                v-model="query.need_interpret"
                :options="options.need_interpret"
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
            v-if="('time' in col && col.time) || ('link' in col && col.link)"
            #default="{ row }"
          >
            <template v-if="'time' in col && col.time">
              {{ formatTime(cellValue(row, col.prop)) }}
            </template>
            <a
              v-else-if="cellValue(row, col.prop)"
              class="source-link"
              :href="hrefOf(cellValue(row, col.prop))"
              target="_blank"
              rel="noopener noreferrer"
            >{{ cellValue(row, col.prop) }}</a>
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
      :title="editing ? '编辑政策基础标签' : '新增政策基础标签'"
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

<style scoped>
.source-link {
  color: var(--zt-blue-600);
  text-decoration: none;
}

.source-link:hover {
  text-decoration: underline;
}
</style>
