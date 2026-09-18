<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { importAfterAreaResolve } from '@/api/codebook'
import {
  createSource,
  downloadPolicy,
  importSources,
  listSources,
  sourceOptions,
  updateSource,
  type SourceItem,
} from '@/api/policy'
import { errorMessage, isApiError } from '@/api/errors'
import { importUi, reportImportResult, runExcelImport } from '@/api/excelImport'
import FilterSelect from '@/components/FilterSelect.vue'
import ListPage from '@/components/ListPage.vue'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'

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
  crawl_priority: '',
  page: 1,
  page_size: 20,
})
const options = reactive({
  site_name: [] as string[],
  province_name: [] as string[],
  city_name: [] as string[],
  tag: [] as string[],
  crawl_priority: [] as string[],
  city_by_province: {} as Record<string, string[]>,
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

const tableColumns = [
  { prop: 'site_name', label: '网站名称', minWidth: 180 },
  { prop: 'province_name', label: '省份', width: 100 },
  { prop: 'city_name', label: '地市', width: 110 },
  { prop: 'district_name', label: '区县', width: 120 },
  { prop: 'crawl_priority', label: '网站梳理和抓取的优先级', minWidth: 200 },
  { prop: 'url', label: '链接', minWidth: 240, link: true },
  { prop: 'tag', label: '标签', minWidth: 180 },
  { prop: 'data_type', label: '数据类型（综合-0、政策-1、新闻-2）注：0和1链接下全爬，2爬聚集板块', minWidth: 360 },
  { prop: 'department', label: '所属部门', minWidth: 200 },
  { prop: 'created_at', label: '入库时间', width: 170, time: true },
  { prop: 'created_by_name', label: '入库人', width: 110 },
  { prop: 'updated_at', label: '更新时间', width: 170, time: true },
  { prop: 'updated_by_name', label: '操作人', width: 110 },
] as const

const cityOptions = computed(() => {
  if (query.province_name && options.city_by_province[query.province_name]) {
    return options.city_by_province[query.province_name]
  }
  return options.city_name
})

function cellValue(row: SourceItem, prop: string): string {
  return String(row[prop as keyof SourceItem] ?? '')
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
    const data = await sourceOptions()
    options.site_name = (data.site_name as string[]) ?? []
    options.province_name = (data.province_name as string[]) ?? []
    options.city_name = (data.city_name as string[]) ?? []
    options.tag = (data.tag as string[]) ?? []
    options.crawl_priority = (data.crawl_priority as string[]) ?? []
    options.city_by_province = (data.city_by_province as Record<string, string[]>) ?? {}
  } catch {
    /* 选项失败不影响列表 */
  }
}

async function load() {
  loading.value = true
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
    await Promise.all([load(), loadOptions()])
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
    const result = await runExcelImport(file, (onProgress) =>
      importAfterAreaResolve(file, importSources, onProgress),
    )
    reportImportResult(result, '信源管理-上传校验.xlsx')
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
  void loadOptions()
})
</script>

<template>
  <div>
    <ListPage
      title="信源管理"
      hint="上传时先补省市区编码再校验：有重复或省市区编码为空则整批不入库，并下载全量打标文件。全部通过后按该区县当前最大网站编码递增。完整流水在「系统管理 / 操作日志」。"
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
            <el-form-item label="网站名称">
              <FilterSelect
                v-model="query.site_name"
                :options="options.site_name"
              />
            </el-form-item>
            <el-form-item label="省份">
              <FilterSelect
                v-model="query.province_name"
                :options="options.province_name"
                size="short"
              />
            </el-form-item>
            <el-form-item label="地市">
              <FilterSelect
                v-model="query.city_name"
                :options="cityOptions"
                size="short"
              />
            </el-form-item>
            <el-form-item label="标签">
              <FilterSelect
                v-model="query.tag"
                :options="options.tag"
              />
            </el-form-item>
            <el-form-item label="网站优先级">
              <FilterSelect
                v-model="query.crawl_priority"
                :options="options.crawl_priority"
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
    <el-dialog
      v-model="visible"
      :title="editing ? '编辑信源' : '新增信源'"
      width="640px"
    >
      <el-form label-position="top">
        <el-form-item
          label="网站名称"
          required
        >
          <el-input v-model="form.site_name" />
        </el-form-item>
        <el-form-item label="省份">
          <el-input v-model="form.province_name" />
        </el-form-item>
        <el-form-item label="地市">
          <el-input v-model="form.city_name" />
        </el-form-item>
        <el-form-item label="区县">
          <el-input v-model="form.district_name" />
        </el-form-item>
        <el-form-item label="网站梳理和抓取的优先级">
          <el-input v-model="form.crawl_priority" />
        </el-form-item>
        <el-form-item label="链接">
          <el-input v-model="form.url" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tag" />
        </el-form-item>
        <el-form-item label="数据类型（综合-0、政策-1、新闻-2）注：0和1链接下全爬，2爬聚集板块">
          <el-input v-model="form.data_type" />
        </el-form-item>
        <el-form-item label="所属部门">
          <el-input v-model="form.department" />
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

<style scoped>
.source-link {
  color: var(--zt-blue-600);
  text-decoration: none;
}

.source-link:hover {
  text-decoration: underline;
}
</style>
