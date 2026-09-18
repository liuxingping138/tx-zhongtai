<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createInterpretation,
  downloadPolicy,
  importInterpretations,
  listInterpretations,
  updateInterpretation,
  type InterpretationItem,
} from '@/api/policy'
import { errorMessage, isApiError } from '@/api/errors'
import ListPage from '@/components/ListPage.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const canWrite = auth.canFull('policy.interpretations')
const canAudit = auth.canRead('system.audit')

const emptyForm = {
  tenant_id: '',
  policy_uid: '',
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

const fieldLabels: Record<keyof typeof emptyForm, string> = {
  tenant_id: '租户ID',
  policy_uid: '政策唯一标识',
  policy_title: '政策原文名称',
  industry_scenario_code: '行业场景编码',
  industry_code: '行业编码',
  industry_l1: '一级行业',
  industry_l2: '二级行业',
  industry_l3: '三级行业',
  scenario_code: '场景编码',
  scenario_l1_name: '一级场景名称',
  scenario_l2_name: '二级场景名称',
  scenario_l3_name: '三级场景名称',
  target_customers: '目标客户',
  opportunity_type: '机会类型',
  policy_summary: '政策要文',
  has_subsidy: '有无政府补贴',
  subsidy_content: '补贴内容',
  market_opportunity: '政策市场机会',
  info_level: '信息化等级',
  is_new_scenario: '是否新增场景',
  new_scenario_level: '新增场景级别',
}

const longFields = new Set(['target_customers', 'policy_summary', 'subsidy_content', 'market_opportunity'])

const loading = ref(false)
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

function formatTime(value: string): string {
  return value.replace('T', ' ').replace(/\.\d+.*$/, '')
}

async function load() {
  loading.value = true
  try {
    const page = await listInterpretations({
      policy_title: query.policy_title || undefined,
      industry_scenario_code: query.industry_scenario_code || undefined,
      industry_l1: query.industry_l1 || undefined,
      opportunity_type: query.opportunity_type || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    items.value = page.items
    total.value = page.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载政策解读失败'))
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
      await updateInterpretation(editing.value.id, { ...payload, version: editing.value.version })
    } else {
      await createInterpretation(payload)
    }
    ElMessage.success('已保存')
    visible.value = false
    await load()
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
    const result = await importInterpretations(file)
    ElMessage.success(`导入完成：新增 ${result.inserted}，跳过 ${result.skipped}`)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

async function onExport() {
  try {
    await downloadPolicy('/policy/interpretations/export', '政策解读表.xlsx')
  } catch {
    ElMessage.error('导出失败')
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'policy.interpretations' } })
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div>
    <ListPage
      title="政策解读表"
      hint="对应《政策解读表》。空的政策唯一标识和关联主键由系统生成。完整流水在「系统管理 / 操作日志」。"
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
          <el-form-item label="政策原文名称">
            <el-input
              v-model="query.policy_title"
              clearable
            />
          </el-form-item>
          <el-form-item label="行业场景编码">
            <el-input
              v-model="query.industry_scenario_code"
              clearable
            />
          </el-form-item>
          <el-form-item label="一级行业">
            <el-input
              v-model="query.industry_l1"
              clearable
            />
          </el-form-item>
          <el-form-item label="机会类型">
            <el-input
              v-model="query.opportunity_type"
              clearable
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
          prop="policy_title"
          label="政策原文名称"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column
          prop="industry_scenario_code"
          label="行业场景编码"
          width="180"
        />
        <el-table-column
          prop="industry_l1"
          label="一级行业"
          width="120"
        />
        <el-table-column
          prop="opportunity_type"
          label="机会类型"
          width="100"
        />
        <el-table-column
          prop="created_by_name"
          label="入库人"
          width="110"
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
    <el-drawer
      v-model="visible"
      :title="editing ? '编辑政策解读' : '新增政策解读'"
      size="640px"
    >
      <el-form label-position="top">
        <el-form-item
          v-for="(label, key) in fieldLabels"
          :key="key"
          :label="label"
        >
          <el-input
            v-model="form[key]"
            :type="longFields.has(key) ? 'textarea' : 'text'"
            :rows="longFields.has(key) ? 3 : undefined"
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
    </el-drawer>
  </div>
</template>
