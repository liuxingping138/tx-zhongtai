<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
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
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'

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
  void loadOptions()
})
</script>

<template>
  <div>
    <ListPage
      title="政策基础标签表"
      hint="对应《政策基础信息表》主表。上传时会先关联省市区编码，有一条关联不上则整批退回。完整流水在「系统管理 / 操作日志」。"
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
          <el-button :disabled="importUi.visible">
            上传 Excel
          </el-button>
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
            issued_at: '当前政策出台时间',
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
.source-link {
  color: var(--zt-blue-600);
  text-decoration: none;
}

.source-link:hover {
  text-decoration: underline;
}
</style>
