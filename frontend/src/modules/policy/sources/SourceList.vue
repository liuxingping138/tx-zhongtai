<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createSource,
  downloadPolicy,
  importSources,
  listSources,
  updateSource,
  type SourceItem,
} from '@/api/policy'
import { errorMessage, isApiError } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const canWrite = auth.canFull('policy.sources')
const canAudit = auth.canRead('system.audit')

const loading = ref(false)
const items = ref<SourceItem[]>([])
const total = ref(0)
const query = reactive({
  site_name: '',
  province_name: '',
  city_name: '',
  tag: '',
  site_code: '',
  page: 1,
  page_size: 20,
})
const visible = ref(false)
const saving = ref(false)
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

function formatTime(value: string): string {
  return value.replace('T', ' ').replace(/\.\d+.*$/, '')
}

async function load() {
  loading.value = true
  try {
    const page = await listSources({
      site_name: query.site_name || undefined,
      province_name: query.province_name || undefined,
      city_name: query.city_name || undefined,
      tag: query.tag || undefined,
      site_code: query.site_code || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    items.value = page.items
    total.value = page.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载信源失败'))
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

function payloadFromForm() {
  return Object.fromEntries(Object.keys(emptyForm).map((key) => [key, form[key as keyof typeof form]]))
}

function openEdit(row: SourceItem) {
  editing.value = row
  Object.assign(form, emptyForm)
  for (const key of Object.keys(emptyForm) as (keyof typeof emptyForm)[]) {
    form[key] = String(row[key] ?? '')
  }
  visible.value = true
}

async function onSave() {
  if (!form.site_name.trim()) {
    ElMessage.warning('请填写网站名称')
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
    await load()
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert('数据已被他人修改或内部唯一 id 冲突，请重新加载。', '无法保存')
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
    const result = await importSources(file)
    ElMessage.success(`导入完成：新增 ${result.inserted}，跳过 ${result.skipped}`)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

async function onExport() {
  try {
    await downloadPolicy('/policy/sources/export', '信源管理.xlsx')
  } catch {
    ElMessage.error('导出失败')
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'policy.sources' } })
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div>
    <el-form
      inline
      @submit.prevent="onSearch"
    >
      <el-form-item label="网站名称">
        <el-input
          v-model="query.site_name"
          clearable
        />
      </el-form-item>
      <el-form-item label="省份">
        <el-input
          v-model="query.province_name"
          clearable
        />
      </el-form-item>
      <el-form-item label="地市">
        <el-input
          v-model="query.city_name"
          clearable
        />
      </el-form-item>
      <el-form-item label="标签">
        <el-input
          v-model="query.tag"
          clearable
        />
      </el-form-item>
      <el-form-item label="网站编码">
        <el-input
          v-model="query.site_code"
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
        <el-button
          v-if="canWrite"
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
      </el-form-item>
    </el-form>
    <p class="hint">
      对应《北京-网站编码梳理》。入库时会纠正误填到地市的区县编码；新增不填网站编码和内部 id，由系统生成。完整流水在「系统管理 / 操作日志」。
    </p>
    <el-table
      v-loading="loading"
      :data="items"
    >
      <el-table-column
        prop="site_code"
        label="网站编码"
        width="140"
      />
      <el-table-column
        prop="site_name"
        label="网站名称"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column
        prop="province_code"
        label="省编码"
        width="80"
      />
      <el-table-column
        prop="city_code"
        label="市编码"
        width="90"
      />
      <el-table-column
        prop="district_code"
        label="区县编码"
        width="100"
      />
      <el-table-column
        prop="tag"
        label="标签"
        min-width="180"
        show-overflow-tooltip
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
    <div class="pager">
      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.page_size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="load"
      />
    </div>
    <el-dialog
      v-model="visible"
      :title="editing ? '编辑信源' : '新增信源'"
      width="640px"
    >
      <el-form label-width="100px">
        <el-form-item
          label="网站名称"
          required
        >
          <el-input v-model="form.site_name" />
        </el-form-item>
        <el-form-item label="省份">
          <el-input v-model="form.province_name" />
        </el-form-item>
        <el-form-item label="省份编码">
          <el-input v-model="form.province_code" />
        </el-form-item>
        <el-form-item label="地市">
          <el-input v-model="form.city_name" />
        </el-form-item>
        <el-form-item label="地市编码">
          <el-input v-model="form.city_code" />
        </el-form-item>
        <el-form-item label="区县">
          <el-input v-model="form.district_name" />
        </el-form-item>
        <el-form-item label="区县编码">
          <el-input v-model="form.district_code" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tag" />
        </el-form-item>
        <el-form-item label="链接">
          <el-input v-model="form.url" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-input v-model="form.crawl_priority" />
        </el-form-item>
        <el-form-item label="数据类型">
          <el-input v-model="form.data_type" />
        </el-form-item>
        <el-form-item label="所属部门">
          <el-input v-model="form.department" />
        </el-form-item>
        <p
          v-if="editing"
          class="hint"
        >
          网站编码 {{ editing.site_code }}，内部 id 将按名称/省/市/标签重算。
        </p>
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

<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  margin: 0 0 12px;
}

.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.el-form-item :deep(.el-upload) {
  margin: 0 8px;
}
</style>
