<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createBaseTag,
  downloadPolicy,
  importBaseTags,
  listBaseTags,
  updateBaseTag,
  type BaseTagItem,
} from '@/api/policy'
import { errorMessage, isApiError } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const canWrite = auth.canFull('policy.base_tags')
const canAudit = auth.canRead('system.audit')

const loading = ref(false)
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

function formatTime(value: string): string {
  return value.replace('T', ' ').replace(/\.\d+.*$/, '')
}

async function load() {
  loading.value = true
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
    items.value = page.items
    total.value = page.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载政策基础标签失败'))
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

function openEdit(row: BaseTagItem) {
  editing.value = row
  Object.assign(form, emptyForm)
  for (const key of Object.keys(emptyForm) as (keyof typeof emptyForm)[]) {
    form[key] = String(row[key] ?? '')
  }
  visible.value = true
}

async function onSave() {
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
    await load()
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
    const result = await importBaseTags(file)
    ElMessage.success(`导入完成：新增 ${result.inserted}，跳过 ${result.skipped}`)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

async function onExport() {
  try {
    await downloadPolicy('/policy/base-tags/export', '政策基础标签表.xlsx')
  } catch {
    ElMessage.error('导出失败')
  }
}

function openLogs() {
  void router.push({ name: 'system-audit', query: { module_code: 'policy.base_tags' } })
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
      <el-form-item label="政策名称">
        <el-input
          v-model="query.policy_name"
          clearable
        />
      </el-form-item>
      <el-form-item label="省份">
        <el-input
          v-model="query.province_name"
          clearable
        />
      </el-form-item>
      <el-form-item label="政策类型">
        <el-input
          v-model="query.policy_types"
          clearable
        />
      </el-form-item>
      <el-form-item label="是否穿透">
        <el-input
          v-model="query.is_penetrate"
          clearable
        />
      </el-form-item>
      <el-form-item label="是否解读">
        <el-input
          v-model="query.need_interpret"
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
      对应《政策基础信息表》主表，不含政策类型枚举。完整流水在「系统管理 / 操作日志」。
    </p>
    <el-table
      v-loading="loading"
      :data="items"
    >
      <el-table-column
        prop="policy_name"
        label="政策名称"
        min-width="220"
        show-overflow-tooltip
      />
      <el-table-column
        prop="province_name"
        label="省份"
        width="90"
      />
      <el-table-column
        prop="policy_types"
        label="政策类型"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column
        prop="is_penetrate"
        label="是否穿透"
        width="90"
      />
      <el-table-column
        prop="need_interpret"
        label="是否解读"
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
    <div class="pager">
      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.page_size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="load"
      />
    </div>
    <el-drawer
      v-model="visible"
      :title="editing ? '编辑政策基础标签' : '新增政策基础标签'"
      size="640px"
    >
      <el-form label-position="top">
        <el-form-item
          v-for="(label, key) in {
            policy_name: '政策名称',
            issuing_dept: '出台部门',
            issuer_industry: '发文机构行业',
            policy_level: '政策层级',
            province_code: '省份编码',
            province_name: '省份名称',
            city_code: '地市编码',
            city_name: '地市名称',
            issued_at: '出台时间',
            policy_types: '政策类型',
            source_url: '原始网站链接',
            is_penetrate: '是否穿透',
            penetrate_words: '穿透词',
            penetrate_score: '穿透词评分',
            need_interpret: '是否解读',
            remark: '备注',
          }"
          :key="key"
          :label="label"
        >
          <el-input
            v-model="form[key as keyof typeof form]"
            :type="['policy_name', 'penetrate_words', 'remark', 'source_url'].includes(key) ? 'textarea' : 'text'"
            :rows="['policy_name', 'penetrate_words', 'remark'].includes(key) ? 3 : undefined"
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
