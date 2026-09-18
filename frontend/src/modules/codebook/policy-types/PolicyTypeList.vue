<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createPolicyType,
  downloadCodebook,
  importPolicyTypes,
  listPolicyTypes,
  updatePolicyType,
  type PolicyTypeItem,
} from '@/api/codebook'
import { errorMessage, isApiError } from '@/api/errors'
import ListPage from '@/components/ListPage.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const canWrite = auth.canFull('codebook.policy_types')
const canAudit = auth.canRead('system.audit')

const loading = ref(false)
const items = ref<PolicyTypeItem[]>([])
const total = ref(0)
const query = reactive({ keyword: '', page: 1, page_size: 20 })
const visible = ref(false)
const saving = ref(false)
const editing = ref<PolicyTypeItem | null>(null)
const form = reactive({ seq_no: '', type_name: '', definition: '' })

function formatTime(value: string): string {
  return value.replace('T', ' ').replace(/\.\d+.*$/, '')
}

async function load() {
  loading.value = true
  try {
    const page = await listPolicyTypes({
      keyword: query.keyword || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    items.value = page.items
    total.value = page.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载政策类型失败'))
  } finally {
    loading.value = false
  }
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
    await load()
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
    const result = await importPolicyTypes(file)
    ElMessage.success(`导入完成：新增 ${result.inserted}，更新 ${result.updated}，跳过 ${result.skipped}`)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

async function onExport() {
  try {
    await downloadCodebook('/codebook/policy-types/export', '政策类型码表.xlsx')
  } catch {
    ElMessage.error('导出失败')
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'codebook.policy_types' } })
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div>
    <ListPage
      title="政策类型码表"
      hint="对应《政策基础信息表》中的「政策类型枚举值」。每条记录的入库/更新人和时间见下表；完整操作流水在「系统管理 / 操作日志」。"
      :total="total"
      :page="query.page"
      :page-size="query.page_size"
      :loading="loading"
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
          <el-button>上传 Excel</el-button>
        </el-upload>
        <el-button @click="onExport">
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
          @submit.prevent="onSearch"
        >
          <el-form-item label="关键字">
            <el-input
              v-model="query.keyword"
              clearable
              placeholder="序号 / 政策类型 / 定义"
            />
          </el-form-item>
          <el-form-item>
            <el-button
              native-type="submit"
              type="primary"
            >
              查询
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
      :title="editing ? '编辑政策类型' : '新增政策类型'"
      width="560px"
    >
      <el-form label-width="90px">
        <el-form-item
          label="序号"
          required
        >
          <el-input v-model="form.seq_no" />
        </el-form-item>
        <el-form-item
          label="政策类型"
          required
        >
          <el-input v-model="form.type_name" />
        </el-form-item>
        <el-form-item label="定义">
          <el-input
            v-model="form.definition"
            type="textarea"
            :rows="6"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">
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
