<script setup lang="ts">
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, type UploadFile } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { errorMessage } from '@/api/errors'
import { uploadProposalFile } from '@/api/thinktank'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import {
  DEPARTMENT_FALLBACK,
  INDUSTRY_FALLBACK,
  joinPipeTags,
  preferOptions,
  PROPOSAL_RESULT_OPTIONS,
  PROVINCE_FALLBACK,
  UPLOAD_ACCEPT,
} from '../shared/options'
import {
  BIDDING_METHOD_FALLBACK,
  OPPORTUNITY_SOURCE_FALLBACK,
  PROPOSAL_TYPE_FALLBACK,
  type ProposalDynamicOptions,
} from './fields'

const props = defineProps<{
  modelValue: boolean
  options?: ProposalDynamicOptions
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  uploaded: []
}>()

const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const emptyForm = () => ({
  proposal_name: '', customer_name: '', proposal_type: '', industry_tags: [] as string[],
  region_tag: '', opportunity_source: '', bidding_method: '', bid_deadline: '',
  owner_dept: '', owner_name: '', quote_amount: '', result_status: '',
  win_amount: '', selling_points: '', remark: '',
})
const form = reactive(emptyForm())

const proposalTypeChoices = computed(() => preferOptions(props.options?.proposal_type, PROPOSAL_TYPE_FALLBACK))
const industryChoices = computed(() => preferOptions(props.options?.industry_tags, INDUSTRY_FALLBACK))
const regionChoices = computed(() => preferOptions(props.options?.region_tag, PROVINCE_FALLBACK))
const sourceChoices = computed(() => preferOptions(props.options?.opportunity_source, OPPORTUNITY_SOURCE_FALLBACK))
const methodChoices = computed(() => preferOptions(props.options?.bidding_method, BIDDING_METHOD_FALLBACK))
const deptChoices = computed(() => preferOptions(props.options?.owner_dept, DEPARTMENT_FALLBACK))
const resultChoices = computed(() => preferOptions(props.options?.result_status, PROPOSAL_RESULT_OPTIONS))

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

watch(() => props.modelValue, open => {
  if (!open) return
  selectedFile.value = null
  Object.assign(form, emptyForm())
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
  if (form.selling_points.trim().length > 100) {
    ElMessage.warning('方案核心卖点摘要不能超过 100 字')
    return
  }
  uploading.value = true
  try {
    await uploadProposalFile(selectedFile.value, {
      proposal_name: form.proposal_name.trim(),
      customer_name: form.customer_name.trim(),
      proposal_type: form.proposal_type.trim(),
      industry_tags: joinPipeTags(form.industry_tags),
      region_tag: form.region_tag,
      opportunity_source: form.opportunity_source.trim(),
      bidding_method: form.bidding_method.trim(),
      bid_deadline: form.bid_deadline || '',
      owner_dept: form.owner_dept.trim(),
      owner_name: form.owner_name.trim(),
      quote_amount: form.quote_amount.trim(),
      result_status: form.result_status,
      win_amount: form.win_amount.trim(),
      selling_points: form.selling_points.trim(),
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
    title="上传方案库文件"
    width="740px"
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
      label-width="112px"
      :disabled="uploading"
    >
      <el-row :gutter="12">
        <el-col :span="24">
          <el-form-item label="方案名称">
            <el-input
              v-model="form.proposal_name"
              maxlength="500"
              placeholder="留空默认使用上传文件名"
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
          <el-form-item label="方案类型">
            <el-select
              v-model="form.proposal_type"
              filterable
              allow-create
              default-first-option
              clearable
              placeholder="留空则归入未定义"
              class="w-full"
            >
              <el-option
                v-for="opt in proposalTypeChoices"
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
          <el-form-item label="商机来源">
            <el-select
              v-model="form.opportunity_source"
              filterable
              allow-create
              default-first-option
              clearable
              placeholder="请选择或输入"
              class="w-full"
            >
              <el-option
                v-for="opt in sourceChoices"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="招标方式">
            <el-select
              v-model="form.bidding_method"
              filterable
              allow-create
              default-first-option
              clearable
              placeholder="请选择或输入"
              class="w-full"
            >
              <el-option
                v-for="opt in methodChoices"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="投标截止日期">
            <el-date-picker
              v-model="form.bid_deadline"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              class="w-full"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="方案负责部门">
            <el-select
              v-model="form.owner_dept"
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
          <el-form-item label="方案负责人">
            <el-input
              v-model="form.owner_name"
              placeholder="请输入负责人"
              clearable
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="报价(万元)">
            <el-input
              v-model="form.quote_amount"
              placeholder="如 120.5"
              clearable
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="结果">
            <el-select
              v-model="form.result_status"
              clearable
              placeholder="请选择"
              class="w-full"
            >
              <el-option
                v-for="opt in resultChoices"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="中标金额(万元)">
            <el-input
              v-model="form.win_amount"
              placeholder="如 115.0"
              clearable
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="核心卖点摘要">
        <el-input
          v-model="form.selling_points"
          type="textarea"
          :rows="2"
          maxlength="100"
          show-word-limit
          placeholder="≤100字方案核心卖点摘要"
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
