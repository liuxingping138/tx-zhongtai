<script setup lang="ts">
import { EditPen } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { ApiRequestError, errorMessage } from '@/api/errors'
import { updateKnowledge, type KnowledgeItem } from '@/api/thinktank'
import DetailFieldTable from '@/components/DetailFieldTable.vue'
import { buildDetailSections } from '@/components/detailSections'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import {
  buildMetaSectionSpecs,
  DETAIL_SYSTEM_COLUMNS,
  displayFileType,
  EDITABLE_FILE_TYPE_OPTIONS,
  EDITOR_GROUPS,
  INDUSTRY_OPTIONS,
  joinPipeTags,
  splitPipeTags,
  TABLE_COLUMNS,
  type MetaFormSpec,
  type TextFieldKey,
} from './fields'

const props = defineProps<{
  item: KnowledgeItem
  provinces: string[]
  editableFileTypes?: string[]
  editableIndustries?: string[]
}>()

const emit = defineEmits<{ updated: [item: KnowledgeItem] }>()

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

const editing = ref(false)
const saving = ref(false)
const saveError = ref('')
const activeSection = ref(0)
const fieldsRef = ref<HTMLElement | null>(null)
const errors = reactive<Record<string, string>>({})

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

function specsForSection(title: string): MetaFormSpec[] {
  return buildMetaSectionSpecs(title, fileTypeChoices.value, canClearFileType.value, industryChoices.value, props.provinces)
}

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

const { dirty, markSaved, canLeave } = useUnsavedForm(
  editing,
  () => ({ ...form, industry_types: [...form.industry_types], product_types: [...form.product_types] }),
  saving,
)

const detailColumns = computed(() => {
  const known = new Set(TABLE_COLUMNS.map(col => col.prop))
  const extra = DETAIL_SYSTEM_COLUMNS.filter(col => !known.has(col.prop))
  return [...TABLE_COLUMNS, ...extra]
})

const sections = computed(() => buildDetailSections(detailColumns.value, EDITOR_GROUPS))
const displayRow = computed(() => ({ ...props.item, file_type: displayFileType(props.item.file_type) }))

function clearErrors() {
  for (const key of Object.keys(errors)) delete errors[key]
}

function startEdit() {
  if (!props.item.can_edit) return
  syncForm(props.item)
  clearErrors()
  saveError.value = ''
  editing.value = true
  markSaved()
}

async function cancelEdit() {
  if (!(await canLeave())) return
  editing.value = false
  saveError.value = ''
  clearErrors()
  syncForm(props.item)
}

function buildPayload() {
  return {
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
  }
}

async function onSave() {
  clearErrors()
  if (!form.file_name.trim()) {
    errors.file_name = '请填写资料名称'
    return
  }
  saving.value = true
  saveError.value = ''
  const snapshot = { ...form, industry_types: [...form.industry_types], product_types: [...form.product_types] }
  try {
    const updated = await updateKnowledge(props.item.id, buildPayload())
    markSaved(snapshot)
    editing.value = false
    emit('updated', updated)
    ElMessage.success('标签保存成功')
  } catch (error) {
    saveError.value = error instanceof ApiRequestError && error.status === 409
      ? '该记录已被其他人修改，请先刷新核对最新内容后再保存。'
      : errorMessage(error, '保存标签失败')
  } finally {
    saving.value = false
  }
}

function jumpTo(index: number) {
  activeSection.value = index
  const container = fieldsRef.value
  const target = container?.querySelectorAll<HTMLElement>('.review__section')[index]
  if (container && target) {
    container.scrollTo({ top: target.offsetTop - container.offsetTop - 12, behavior: 'smooth' })
  }
}

watch(
  () => props.item,
  (val) => {
    editing.value = false
    saveError.value = ''
    clearErrors()
    syncForm(val)
    activeSection.value = 0
  },
  { immediate: true },
)

defineExpose({ editing, dirty, startEdit, cancelEdit, confirmDiscard: canLeave })
</script>

<template>
  <section class="review__panel">
    <nav
      class="review__tabs"
      aria-label="字段分组"
    >
      <div class="review__tab-list">
        <button
          v-for="(section, index) in sections"
          :key="section.title || index"
          type="button"
          class="review__tab"
          :class="{ 'is-active': activeSection === index }"
          @click="jumpTo(index)"
        >
          {{ section.title }}
        </button>
      </div>
      <el-button
        v-if="item.can_edit && !editing"
        size="small"
        :icon="EditPen"
        @click="startEdit"
      >
        编辑
      </el-button>
    </nav>

    <div
      ref="fieldsRef"
      class="review__fields"
    >
      <section
        v-for="(section, index) in sections"
        :key="section.title || index"
        class="review__section"
      >
        <div
          v-if="editing && specsForSection(section.title).length"
          class="review__editor"
        >
          <div class="review__section-head">
            <h2 class="review__section-title">
              {{ section.title }}
            </h2>
            <span class="review__editing-tag">编辑中</span>
          </div>
          <div class="review__editor-grid">
            <label
              v-for="spec in specsForSection(section.title)"
              :key="spec.key"
              class="review__field"
              :class="{ 'is-span': spec.span }"
            >
              <span class="review__field-label">
                <em
                  v-if="spec.required"
                  class="review__req"
                >*</em>{{ spec.label }}
              </span>
              <el-select
                v-if="spec.kind === 'multi'"
                v-model="form[spec.key as 'industry_types' | 'product_types']"
                multiple
                filterable
              >
                <el-option
                  v-for="opt in spec.options"
                  :key="opt"
                  :label="opt"
                  :value="opt"
                />
              </el-select>
              <el-select
                v-else-if="spec.kind === 'select'"
                v-model="form[spec.key as TextFieldKey]"
                filterable
                :clearable="spec.clearable"
              >
                <el-option
                  v-for="opt in spec.options"
                  :key="opt"
                  :label="opt"
                  :value="opt"
                />
              </el-select>
              <el-input
                v-else-if="spec.kind === 'textarea'"
                v-model="form[spec.key as TextFieldKey]"
                type="textarea"
                :rows="3"
              />
              <el-input
                v-else
                v-model="form[spec.key as TextFieldKey]"
                @input="delete errors[spec.key]"
              />
              <span
                v-if="errors[spec.key]"
                class="review__field-err"
              >{{ errors[spec.key] }}</span>
            </label>
          </div>
        </div>

        <template v-else>
          <h2
            v-if="section.title"
            class="review__section-title"
          >
            {{ section.title }}
          </h2>
          <DetailFieldTable
            :row="displayRow"
            :fields="section.fields"
          />
        </template>
      </section>
    </div>

    <footer
      v-if="editing"
      class="review__edit-bar"
    >
      <el-alert
        v-if="saveError"
        :title="saveError"
        type="error"
        :closable="false"
        show-icon
      />
      <span
        v-else-if="dirty"
        class="review__dirty"
      >有未保存的修改</span>
      <div class="review__edit-actions">
        <el-button @click="cancelEdit">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          :disabled="!dirty"
          @click="onSave"
        >
          保存
        </el-button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.review__panel { min-height: 0; display: flex; flex-direction: column; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 10px; overflow: hidden; }
.review__tabs { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 16px; border-bottom: 1px solid var(--zt-border); background: var(--zt-soft); }
.review__tab-list { display: flex; gap: 4px; flex-wrap: wrap; }
.review__tab { padding: 4px 12px; border: none; border-radius: 6px; background: transparent; color: var(--zt-ink-700); font-size: 13px; cursor: pointer; }
.review__tab:hover { background: var(--zt-border); color: var(--zt-ink-900); }
.review__tab.is-active { background: var(--zt-panel); color: var(--zt-blue-600); font-weight: 600; }
.review__fields { flex: 1; min-height: 0; overflow: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 20px; }
.review__section { display: flex; flex-direction: column; gap: 8px; }
.review__section-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.review__section-title { margin: 0; font-size: 13px; font-weight: 600; color: var(--zt-ink-700); }
.review__editing-tag { padding: 4px 8px; border-radius: 999px; background: var(--zt-blue-600); color: var(--zt-panel); font-size: 12px; font-weight: 600; }
.review__editor { display: flex; flex-direction: column; gap: 12px; padding: 16px; border: 1.5px solid var(--zt-blue-600); border-radius: 10px; background: var(--zt-row-hover); }
.review__editor-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 16px; }
.review__field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.review__field.is-span { grid-column: 1 / -1; }
.review__field-label { font-size: 13px; font-weight: 500; color: var(--zt-ink-700); }
.review__req { margin-right: 4px; color: var(--zt-danger); font-style: normal; }
.review__field-err { font-size: 12px; color: var(--zt-danger); }
.review__edit-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 20px; border-top: 1px solid var(--zt-border); background: var(--zt-soft); }
.review__dirty { font-size: 13px; color: var(--zt-ink-700); }
.review__edit-actions { margin-left: auto; display: flex; gap: 8px; }
@media (max-width: 767px) {
  .review__editor-grid { grid-template-columns: 1fr; }
}
</style>
