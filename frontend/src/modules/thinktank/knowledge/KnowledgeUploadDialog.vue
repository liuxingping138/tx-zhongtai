<script setup lang="ts">
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, type UploadFile } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { errorMessage } from '@/api/errors'
import { uploadKnowledgeFile } from '@/api/thinktank'
import {
  EDITABLE_FILE_TYPE_OPTIONS,
  INDUSTRY_OPTIONS,
  MARKET_CATEGORY_OPTIONS,
  OPERATOR_OPTIONS,
  PRODUCT_TYPE_OPTIONS,
  joinPipeTags,
} from './fields'

const props = defineProps<{
  modelValue: boolean
  provinces: string[]
  editableFileTypes: string[]
  editableIndustries: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  uploaded: []
}>()

const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const form = reactive({
  file_type: '',
  operator_type: '',
  depart_affiliation: '',
  industry_types: [] as string[],
  app_scenario: '',
  market_category: '',
  product_types: [] as string[],
  product_sub_type: '',
  prov_name: '',
  data_time: '',
  remark: '',
})

const fileTypeChoices = computed(() => {
  if (!props.editableFileTypes.length) return [...EDITABLE_FILE_TYPE_OPTIONS]
  return EDITABLE_FILE_TYPE_OPTIONS.filter(t => props.editableFileTypes.includes(t))
})

const industryChoices = computed(() => {
  if (!props.editableIndustries.length) return [...INDUSTRY_OPTIONS]
  return INDUSTRY_OPTIONS.filter(i => props.editableIndustries.includes(i))
})

watch(() => props.modelValue, open => {
  if (!open) return
  selectedFile.value = null
  Object.assign(form, {
    file_type: '',
    operator_type: '',
    depart_affiliation: '',
    industry_types: [],
    app_scenario: '',
    market_category: '',
    product_types: [],
    product_sub_type: '',
    prov_name: '',
    data_time: '',
    remark: '',
  })
})

function onPickFile(uploadFile: UploadFile) {
  selectedFile.value = uploadFile.raw ?? null
  return false
}

async function onSubmit() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择需要上传的文件')
    return
  }
  uploading.value = true
  try {
    await uploadKnowledgeFile(selectedFile.value, {
      file_type: form.file_type,
      operator_type: form.operator_type,
      depart_affiliation: form.depart_affiliation.trim(),
      industry_type: joinPipeTags(form.industry_types),
      app_scenario: form.app_scenario.trim(),
      market_category: form.market_category,
      product_type: joinPipeTags(form.product_types),
      product_sub_type: form.product_sub_type.trim(),
      prov_name: form.prov_name,
      data_time: form.data_time.trim(),
      remark: form.remark.trim(),
    })
    ElMessage.success('上传成功')
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
    title="上传知识库文件"
    width="640px"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-upload
      drag
      :auto-upload="false"
      :show-file-list="false"
      accept=".pdf,.xlsx,.xls,.docx,.doc,.pptx,.ppt,.txt,.csv,.md"
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
      label-width="92px"
      :disabled="uploading"
    >
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="文件类型">
            <el-select
              v-model="form.file_type"
              clearable
              placeholder="留空则归入未定义"
              class="w-full"
            >
              <el-option
                v-for="item in fileTypeChoices"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="行业类型">
            <el-select
              v-model="form.industry_types"
              multiple
              collapse-tags
              clearable
              placeholder="留空视为「无」"
              class="w-full"
            >
              <el-option
                v-for="item in industryChoices"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="运营商类型">
            <el-select
              v-model="form.operator_type"
              clearable
              placeholder="请选择"
              class="w-full"
            >
              <el-option
                v-for="item in OPERATOR_OPTIONS"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="市场类别">
            <el-select
              v-model="form.market_category"
              clearable
              placeholder="请选择"
              class="w-full"
            >
              <el-option
                v-for="item in MARKET_CATEGORY_OPTIONS"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="产品类型">
            <el-select
              v-model="form.product_types"
              multiple
              collapse-tags
              clearable
              placeholder="请选择"
              class="w-full"
            >
              <el-option
                v-for="item in PRODUCT_TYPE_OPTIONS"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="省份">
            <el-select
              v-model="form.prov_name"
              filterable
              clearable
              placeholder="请选择"
              class="w-full"
            >
              <el-option
                v-for="item in provinces"
                :key="item"
                :label="item"
                :value="item"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="部门归属">
            <el-input
              v-model="form.depart_affiliation"
              placeholder="请输入部门名称"
              clearable
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="资料时间">
            <el-input
              v-model="form.data_time"
              placeholder="如 2026/6"
              clearable
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="产品子类型">
            <el-input
              v-model="form.product_sub_type"
              placeholder="多项用|分隔"
              clearable
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="应用场景">
            <el-input
              v-model="form.app_scenario"
              placeholder="请输入应用场景"
              clearable
            />
          </el-form-item>
        </el-col>
      </el-row>
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
        @click="$emit('update:modelValue', false)"
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
