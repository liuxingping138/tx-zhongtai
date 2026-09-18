<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  downloadCodebook,
  importScenarios,
  listScenarios,
  updateScenario,
  type ScenarioItem,
} from '@/api/codebook'
import { errorMessage, isApiError } from '@/api/errors'
import ListPage from '@/components/ListPage.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const canWrite = auth.canFull('codebook.scenarios')
const canAudit = auth.canRead('system.audit')

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
const editing = ref<ScenarioItem | null>(null)
const form = reactive<Record<string, string>>({})

function formatTime(value: string): string {
  return value.replace('T', ' ').replace(/\.\d+.*$/, '')
}

async function load() {
  loading.value = true
  try {
    const page = await listScenarios({
      industry_scenario_code: query.industry_scenario_code || undefined,
      industry_l1: query.industry_l1 || undefined,
      scenario_tag: query.scenario_tag || undefined,
      customer_group_name: query.customer_group_name || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    items.value = page.items
    total.value = page.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载场景码表失败'))
  } finally {
    loading.value = false
  }
}

function onSearch() {
  query.page = 1
  void load()
}

function openEdit(row: ScenarioItem) {
  editing.value = row
  for (const field of fields) {
    form[field.key] = String(row[field.key] ?? '')
  }
  visible.value = true
}

async function onSave() {
  if (!editing.value) {
    return
  }
  saving.value = true
  try {
    await updateScenario(editing.value.id, { ...form, version: editing.value.version })
    ElMessage.success('已保存')
    visible.value = false
    await load()
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert('数据已被他人修改，请重新加载后再编辑。', '版本冲突')
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
    const result = await importScenarios(file)
    ElMessage.success(`导入完成：新增 ${result.inserted}，跳过重复 ${result.skipped}`)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

async function onExport() {
  try {
    await downloadCodebook('/codebook/scenarios/export', '行业场景字典表.xlsx')
  } catch {
    ElMessage.error('导出失败')
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'codebook.scenarios' } })
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div>
    <ListPage
      title="行业场景码表"
      hint="对应《行业场景字典表》。重复上传同一行会按内容去重。入库/更新人和时间见下表；完整流水在「系统管理 / 操作日志」。"
      :total="total"
      :page="query.page"
      :page-size="query.page_size"
      :loading="loading"
      @update:page="query.page = $event"
      @update:page-size="query.page_size = $event"
      @change="load"
    >
      <template #actions>
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
          <el-form-item label="场景标签">
            <el-input
              v-model="query.scenario_tag"
              clearable
            />
          </el-form-item>
          <el-form-item label="客群名称">
            <el-input
              v-model="query.customer_group_name"
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
          prop="industry_scenario_code"
          label="行业场景编码"
          width="180"
        />
        <el-table-column
          prop="industry_l1"
          label="一级行业"
          width="140"
        />
        <el-table-column
          prop="scenario_tag"
          label="场景标签"
          min-width="160"
        />
        <el-table-column
          prop="scenario_level"
          label="level"
          width="70"
        />
        <el-table-column
          prop="customer_group_name"
          label="客群名称"
          width="160"
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
          prop="updated_by_name"
          label="操作人"
          width="110"
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
    <el-drawer
      v-model="visible"
      title="编辑场景码表"
      size="640px"
    >
      <el-form label-position="top">
        <el-form-item
          v-for="field in fields"
          :key="field.key"
          :label="field.label"
        >
          <el-input
            v-model="form[field.key]"
            :type="longFields.has(field.key) ? 'textarea' : 'text'"
            :rows="longFields.has(field.key) ? 3 : undefined"
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
