<script setup lang="ts">
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, type UploadFile } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { errorMessage } from '@/api/errors'
import { uploadReportFile } from '@/api/thinktank'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import {
  DEPARTMENT_FALLBACK,
  INDUSTRY_FALLBACK,
  joinPipeTags,
  preferOptions,
  PROVINCE_FALLBACK,
  UPLOAD_ACCEPT,
  YES_NO_OPTIONS,
} from '../shared/options'
import { REPORT_TYPE_FALLBACK, type ReportDynamicOptions } from './fields'

const props = defineProps<{
  modelValue: boolean
  options?: ReportDynamicOptions
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  uploaded: []
}>()

const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const form = reactive({
  report_name: '',
  project_name: '',
  customer_name: '',
  report_type: '',
  industry_tags: [] as string[],
  region_tag: '',
  delivery_dept: '',
  participants: '',
  is_temp_support: '',
  delivery_date: '',
  summary: '',
  keywords: '',
  data_sources: '',
  remark: '',
})

const reportTypeChoices = computed(() => preferOptions(props.options?.report_type, REPORT_TYPE_FALLBACK))
const industryChoices = computed(() => preferOptions(props.options?.industry_tags, INDUSTRY_FALLBACK))
const regionChoices = computed(() => preferOptions(props.options?.region_tag, PROVINCE_FALLBACK))
const deptChoices = computed(() => preferOptions(props.options?.delivery_dept, DEPARTMENT_FALLBACK))
const tempSupportChoices = computed(() => preferOptions(props.options?.is_temp_support, YES_NO_OPTIONS))

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

watch(() => props.modelValue, open => {
  if (!open) return
  selectedFile.value = null
  Object.assign(form, {
    report_name: '',
    project_name: '',
    customer_name: '',
    report_type: '',
    industry_tags: [],
    region_tag: '',
    delivery_dept: '',
    participants: '',
    is_temp_support: '',
    delivery_date: '',
    summary: '',
    keywords: '',
    data_sources: '',
    remark: '',
  })
}, { flush: 'sync' })

const { markSaved, close: closeDialog, beforeClose } = useUnsavedForm(
  visible,
  () => ({ file: selectedFile.value?.name ?? '', ...form, industry_tags: [...form.industry_tags] }),
  uploading,
)

function onPickFile(uploadFile: UploadFile) {
  selectedFile.value = uploadFile.raw ?? null
  return false
}

async function onSubmit() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择需要上传的文件')
    return
  }
  if (form.summary.trim().length > 100) {
    ElMessage.warning('核心结论摘要不能超过 100 字')
    return
  }
  uploading.value = true
  try {
    await uploadReportFile(selectedFile.value, {
      report_name: form.report_name.trim(),
      project_name: form.project_name.trim(),
      customer_name: form.customer_name.trim(),
      report_type: form.report_type.trim(),
      industry_tags: joinPipeTags(form.industry_tags),
      region_tag: form.region_tag,
      delivery_dept: form.delivery_dept.trim(),
      participants: form.participants.trim(),
      is_temp_support: form.is_temp_support,
      delivery_date: form.delivery_date || '',
      summary: form.summary.trim(),
      keywords: form.keywords.trim(),
      data_sources: form.data_sources.trim(),
      remark: form.remark.trim(),
    })
    ElMessage.success('上传成功')
    markSaved()
    emit('update:modelValue', false)
    emit('uploaded')
  } catch (error) {
    ElMessage.error(errorMessage(error, '上传失败'))
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="上传报告库文件"
    width="720px"
    destroy-on-close
    :close-on-click-modal="!uploading"
    :close-on-press-escape="!uploading"
    :show-close="!uploading"
    :before-close="beforeClose"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-upload
      drag
      :auto-upload="false"
      :show-file-list="false"
      :accept="UPLOAD_ACCEPT"
      :on-change="onPickFile"
    >
      <el-icon class="el-icon--upload">
        <UploadFilled />
      </el-icon>
      <div class="el-upload__text">
        {{ selectedFile ? `已选择：${selectedFile.name}` : '拖拽文件到此，或点击选择 PDF / Word / PPT / Excel（50MB 以内）' }}
      </div>
    </el-upload>

    <el-form
      class="upload-tags-form"
      label-width="108px"
      :disabled="uploading"
    >
      <el-row :gutter="12">
        <el-col :span="24">
          <el-form-item label="报告名称">
            <el-input
              v-model="form.report_name"
              maxlength="500"
              placeholder="留空默认使用上传文件名"
              clearable
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="所属项目">
            <el-input
              v-model="form.project_name"
              placeholder="请输入所属项目"
              clearable
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="客户名称">
            <el-input
              v-model="form.customer_name"
              placeholder="请输入客户名称"
              clearable
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="报告类型">
            <el-select
              v-model="form.report_type"
              filterable
              allow-create
              default-first-option
              clearable
              placeholder="留空则归入未定义"
              class="w-full"
            >
              <el-option
                v-for="opt in reportTypeChoices"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="行业赛道标签">
            <el-select
              v-model="form.industry_tags"
              multiple
              filterable
              collapse-tags
              clearable
              placeholder="可多选"
              class="w-full"
            >
              <el-option
                v-for="opt in industryChoices"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="区域标签">
            <el-select
              v-model="form.region_tag"
              filterable
              clearable
              placeholder="请选择区域"
              class="w-full"
            >
              <el-option
                v-for="opt in regionChoices"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="交付部门">
            <el-select
              v-model="form.delivery_dept"
              filterable
              allow-create
              default-first-option
              clearable
              placeholder="请选择或输入部门"
              class="w-full"
            >
              <el-option
                v-for="opt in deptChoices"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="参与人员">
            <el-input
              v-model="form.participants"
              placeholder="多位人员用逗号或顿号分隔"
              clearable
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="是否临时支撑">
            <el-select
              v-model="form.is_temp_support"
              clearable
              placeholder="请选择"
              class="w-full"
            >
              <el-option
                v-for="opt in tempSupportChoices"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="交付日期">
            <el-date-picker
              v-model="form.delivery_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              class="w-full"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="关键词(3-5个)">
            <el-input
              v-model="form.keywords"
              placeholder="3-5个关键词，逗号分隔"
              clearable
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="核心结论摘要">
        <el-input
          v-model="form.summary"
          type="textarea"
          :rows="2"
          maxlength="100"
          show-word-limit
          placeholder="≤100字核心结论摘要"
        />
      </el-form-item>
      <el-form-item label="主要数据来源">
        <el-input
          v-model="form.data_sources"
          type="textarea"
          :rows="2"
          placeholder="如统计局、行业白皮书、客户调研等"
        />
      </el-form-item>
      <el-form-item label="备注">
        <el-input
          v-model="form.remark"
          type="textarea"
          :rows="2"
          placeholder="可选"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button
        :disabled="uploading"
        @click="closeDialog"
      >
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="uploading"
        @click="onSubmit"
      >
        确认上传
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.upload-tags-form { margin-top: 16px; }
.w-full { width: 100%; }
</style>
