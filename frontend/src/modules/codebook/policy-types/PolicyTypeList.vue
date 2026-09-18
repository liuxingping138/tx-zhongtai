<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createPolicyType,
  downloadCodebook,
  importPolicyTypes,
  listPolicyTypes,
  policyTypeOptions,
  updatePolicyType,
  type PolicyTypeItem,
} from '@/api/codebook'
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
const canWrite = computed(() => auth.canFull('codebook.policy_types'))
const canAudit = computed(() => auth.canRead('system.audit'))

const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const items = ref<PolicyTypeItem[]>([])
const total = ref(0)
const query = reactive({ keyword: '', page: 1, page_size: 20 })
const typeOptions = ref<string[]>([])
const visible = ref(false)
const saving = ref(false)
const editing = ref<PolicyTypeItem | null>(null)
const form = reactive({ seq_no: '', type_name: '', definition: '' })

async function loadOptions() {
  try {
    const data = await policyTypeOptions()
    typeOptions.value = data.type_name ?? []
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
    const page = await listPolicyTypes({
      keyword: query.keyword || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    if (sequence !== loadSequence) return
    items.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = errorMessage(error, '加载政策类型失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function onResetFilters() {
  query.keyword = ''
  onSearch()
}

function onSearch() {
  query.page = 1
  void load()
}

function openCreate() {
  editing.value = null
  form.seq_no = ''
  form.type_name = ''
  form.definition = ''
  visible.value = true
}

function openEdit(row: PolicyTypeItem) {
  editing.value = row
  form.seq_no = row.seq_no
  form.type_name = row.type_name
  form.definition = row.definition
  visible.value = true
}

async function onSave() {
  if (saving.value) return
  if (!form.type_name.trim()) {
    ElMessage.warning('请填写政策类型')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await updatePolicyType(editing.value.id, { ...form, version: editing.value.version })
    } else {
      await createPolicyType(form)
    }
    ElMessage.success('已保存')
    visible.value = false
    await Promise.all([load(), loadOptions()])
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert('数据已被他人修改或政策类型重复，请重新加载。', '无法保存')
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
    const result = await runExcelImport(file, (onProgress) => importPolicyTypes(file, onProgress))
    reportImportResult(result, '政策类型-跳过明细.xlsx')
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
    await downloadCodebook('/codebook/policy-types/export', '政策类型码表.xlsx')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'codebook.policy_types' } })
}

onMounted(() => {
  void load()
  void loadOptions()
})

const editorGroups: EditorGroup[] = [
  {
    "title": "类型信息",
    "hint": "政策类型为必填项，序号可按现有码表约定填写。",
    "fields": [
      {
        "key": "seq_no",
        "label": "序号",
        "maxLength": 32
      },
      {
        "key": "type_name",
        "label": "政策类型",
        "required": true,
        "maxLength": 64
      },
      {
        "key": "definition",
        "label": "定义",
        "long": true,
        "hint": "说明此类型的含义和适用范围，方便团队统一理解。"
      }
    ]
  }
]
const editorGuard = useUnsavedForm(visible, () => form, saving)
</script>

<template>
  <div>
    <ListPage
      title="政策类型码表"
      hint="维护政策分类及定义，统一业务口径。"
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
            content="上传 .xlsx 文件，重复或校验不通过的记录会跳过，详情见导入结果。"
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
            <el-form-item label="关键字">
              <FilterSelect
                v-model="query.keyword"
                :options="typeOptions"
                placeholder="输入或选择政策类型"
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
          prop="seq_no"
          label="序号"
          width="80"
        />
        <el-table-column
          prop="type_name"
          label="政策类型"
          width="160"
        />
        <el-table-column
          prop="definition"
          label="定义"
          min-width="280"
          show-overflow-tooltip
        />
        <el-table-column
          label="入库时间"
          width="170"
        >
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="created_by_name"
          label="入库人"
          width="120"
        />
        <el-table-column
          label="更新时间"
          width="170"
        >
          <template #default="{ row }">
            {{ formatTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="updated_by_name"
          label="操作人"
          width="120"
        />
        <el-table-column
          v-if="canWrite"
          label="操作"
          width="80"
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
    <el-dialog
      v-model="visible"
      class="editor-overlay"
      :before-close="editorGuard.beforeClose"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      :title="editing ? '编辑政策类型' : '新增政策类型'"
      width="560px"
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
    </el-dialog>
  </div>
</template>
