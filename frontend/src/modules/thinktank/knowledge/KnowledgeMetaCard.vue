<script setup lang="ts">
import { Edit } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { errorMessage } from '@/api/errors'
import { updateKnowledge, type KnowledgeItem } from '@/api/thinktank'
import {
  displayFileType,
  EDITABLE_FILE_TYPE_OPTIONS,
  INDUSTRY_OPTIONS,
  joinPipeTags,
  MARKET_CATEGORY_OPTIONS,
  OPERATOR_OPTIONS,
  PRODUCT_TYPE_OPTIONS,
  splitPipeTags,
} from './fields'

const props = defineProps<{
  item: KnowledgeItem
  provinces: string[]
  editableFileTypes?: string[]
  editableIndustries?: string[]
}>()

const fileTypeChoices = computed(() =>
  props.editableFileTypes
    ? EDITABLE_FILE_TYPE_OPTIONS.filter(t => props.editableFileTypes?.includes(t))
    : [...EDITABLE_FILE_TYPE_OPTIONS],
)
const canClearFileType = computed(() => !props.editableFileTypes || props.editableFileTypes.includes('未定义'))
const industryChoices = computed(() =>
  props.editableIndustries
    ? INDUSTRY_OPTIONS.filter(i => props.editableIndustries?.includes(i))
    : [...INDUSTRY_OPTIONS],
)

const emit = defineEmits<{ updated: [item: KnowledgeItem] }>()

const editing = ref(false)
const saving = ref(false)
const form = reactive({
  file_name: '',
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

function syncForm(record: KnowledgeItem) {
  Object.assign(form, {
    file_name: record.file_name,
    file_type: record.file_type,
    operator_type: record.operator_type,
    depart_affiliation: record.depart_affiliation,
    industry_types: splitPipeTags(record.industry_type),
    app_scenario: record.app_scenario,
    market_category: record.market_category,
    product_types: splitPipeTags(record.product_type),
    product_sub_type: record.product_sub_type,
    prov_name: record.prov_name,
    data_time: record.data_time,
    remark: record.remark,
  })
}

watch(() => props.item, val => syncForm(val), { immediate: true })

async function onSave() {
  saving.value = true
  try {
    const updated = await updateKnowledge(props.item.id, {
      file_name: form.file_name.trim(),
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
      version: props.item.version,
    })
    editing.value = false
    emit('updated', updated)
    ElMessage.success('标签保存成功')
  } catch (error) {
    ElMessage.error(errorMessage(error, '保存标签失败'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-card
    class="meta-card"
    shadow="never"
  >
    <template #header>
      <div class="meta-header">
        <span>资料标签信息</span>
        <div v-if="item.can_edit">
          <el-button
            v-if="!editing"
            size="small"
            type="primary"
            plain
            :icon="Edit"
            @click="editing = true"
          >
            编辑
          </el-button>
          <template v-else>
            <el-button
              size="small"
              :disabled="saving"
              @click="editing = false; syncForm(item)"
            >
              取消
            </el-button>
            <el-button
              size="small"
              type="primary"
              :loading="saving"
              @click="onSave"
            >
              保存
            </el-button>
          </template>
        </div>
      </div>
    </template>

    <el-form
      label-width="88px"
      label-position="left"
      size="small"
      :disabled="saving"
    >
      <el-form-item label="资料名称">
        <el-input
          v-if="editing"
          v-model="form.file_name"
        />
        <span v-else>{{ item.file_name }}</span>
      </el-form-item>
      <el-form-item label="文件类型">
        <el-select
          v-if="editing"
          v-model="form.file_type"
          :clearable="canClearFileType"
          class="w-full"
        >
          <el-option
            v-for="t in fileTypeChoices"
            :key="t"
            :label="t"
            :value="t"
          />
        </el-select>
        <span v-else>{{ displayFileType(item.file_type) }}</span>
      </el-form-item>
      <el-form-item label="运营商类型">
        <el-select
          v-if="editing"
          v-model="form.operator_type"
          clearable
          class="w-full"
        >
          <el-option
            v-for="t in OPERATOR_OPTIONS"
            :key="t"
            :label="t"
            :value="t"
          />
        </el-select>
        <span v-else>{{ item.operator_type || '-' }}</span>
      </el-form-item>
      <el-form-item label="部门归属">
        <el-input
          v-if="editing"
          v-model="form.depart_affiliation"
        />
        <span v-else>{{ item.depart_affiliation || '-' }}</span>
      </el-form-item>
      <el-form-item label="行业类型">
        <el-select
          v-if="editing"
          v-model="form.industry_types"
          multiple
          collapse-tags
          class="w-full"
        >
          <el-option
            v-for="t in industryChoices"
            :key="t"
            :label="t"
            :value="t"
          />
        </el-select>
        <span v-else>{{ item.industry_type || '无' }}</span>
      </el-form-item>
      <el-form-item label="应用场景">
        <el-input
          v-if="editing"
          v-model="form.app_scenario"
        />
        <span v-else>{{ item.app_scenario || '-' }}</span>
      </el-form-item>
      <el-form-item label="市场类别">
        <el-select
          v-if="editing"
          v-model="form.market_category"
          clearable
          class="w-full"
        >
          <el-option
            v-for="t in MARKET_CATEGORY_OPTIONS"
            :key="t"
            :label="t"
            :value="t"
          />
        </el-select>
        <span v-else>{{ item.market_category || '-' }}</span>
      </el-form-item>
      <el-form-item label="产品类型">
        <el-select
          v-if="editing"
          v-model="form.product_types"
          multiple
          collapse-tags
          class="w-full"
        >
          <el-option
            v-for="t in PRODUCT_TYPE_OPTIONS"
            :key="t"
            :label="t"
            :value="t"
          />
        </el-select>
        <span v-else>{{ item.product_type || '-' }}</span>
      </el-form-item>
      <el-form-item label="产品子类型">
        <el-input
          v-if="editing"
          v-model="form.product_sub_type"
        />
        <span v-else>{{ item.product_sub_type || '-' }}</span>
      </el-form-item>
      <el-form-item label="省份">
        <el-select
          v-if="editing"
          v-model="form.prov_name"
          filterable
          clearable
          class="w-full"
        >
          <el-option
            v-for="p in provinces"
            :key="p"
            :label="p"
            :value="p"
          />
        </el-select>
        <span v-else>{{ item.prov_name || '-' }}</span>
      </el-form-item>
      <el-form-item label="资料时间">
        <el-input
          v-if="editing"
          v-model="form.data_time"
        />
        <span v-else>{{ item.data_time || '-' }}</span>
      </el-form-item>
      <el-form-item label="备注">
        <el-input
          v-if="editing"
          v-model="form.remark"
          type="textarea"
          :rows="2"
        />
        <span v-else>{{ item.remark || '-' }}</span>
      </el-form-item>
      <el-form-item label="上传人">
        <span>{{ item.created_by_name }} · {{ item.uploaded_at }}</span>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.meta-card { overflow-y: auto; border-color: var(--zt-border); }
.meta-header { display: flex; align-items: center; justify-content: space-between; font-weight: 600; }
.w-full { width: 100%; }
</style>
