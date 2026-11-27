<script setup lang="ts" generic="T extends { id: string; version: number; can_edit: boolean }">
import { EditPen } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import { errorMessage, isStaleConflict, markShown } from '@/api/errors'
import type { DataColumn } from '@/components/dataColumns'
import DetailFieldTable from '@/components/DetailFieldTable.vue'
import { buildDetailSections } from '@/components/detailSections'
import type { EditorGroup } from '@/components/editorGroups'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import type { SharedMetaFieldSpec } from './metaFieldSpec'
import { joinPipeTags, splitPipeTags } from './options'

type FormMap = Record<string, string | string[]>

const props = defineProps<{
  item: T
  displayRow?: Record<string, unknown>
  tableColumns: readonly DataColumn[]
  systemColumns: readonly DataColumn[]
  editorGroups: readonly EditorGroup[]
  specsBySection: Record<string, readonly SharedMetaFieldSpec[]>
  multiKeys?: readonly string[]
  validate: (values: FormMap) => Record<string, string>
  save: (id: string, payload: Record<string, unknown> & { version: number }) => Promise<T>
}>()

const emit = defineEmits<{ updated: [item: T] }>()

const editing = ref(false)
const saving = ref(false)
const saveError = ref('')
const activeSection = ref(0)
const fieldsRef = ref<HTMLElement | null>(null)
const errors = reactive<Record<string, string>>({})
const form = reactive<FormMap>({})

const multiKeySet = computed(() => new Set(props.multiKeys ?? []))
const allSpecs = computed(() => Object.values(props.specsBySection).flat())

function syncForm(record: T) {
  const rec = record as unknown as Record<string, unknown>
  for (const spec of allSpecs.value) {
    const raw = typeof rec[spec.key] === 'string' ? rec[spec.key] as string : ''
    form[spec.key] = multiKeySet.value.has(spec.key) ? splitPipeTags(raw) : raw
  }
}

function captureSnapshot(): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = {}
  for (const spec of allSpecs.value) {
    const val = form[spec.key]
    out[spec.key] = Array.isArray(val) ? [...val] : (val ?? '')
  }
  return out
}

const { dirty, markSaved, canLeave } = useUnsavedForm(editing, captureSnapshot, saving)

const detailColumns = computed(() => {
  const known = new Set(props.tableColumns.map(col => col.prop))
  const extra = props.systemColumns.filter(col => !known.has(col.prop))
  return [...props.tableColumns, ...extra]
})

const sections = computed(() => buildDetailSections(detailColumns.value, props.editorGroups))
const rowForDisplay = computed(() => props.displayRow ?? (props.item as unknown as Record<string, unknown>))

function specsForSection(title: string): readonly SharedMetaFieldSpec[] {
  return props.specsBySection[title] ?? []
}

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

function buildPayload(): Record<string, unknown> & { version: number } {
  const payload: Record<string, unknown> = { version: props.item.version }
  for (const spec of allSpecs.value) {
    const val = form[spec.key]
    if (multiKeySet.value.has(spec.key)) {
      payload[spec.key] = joinPipeTags(Array.isArray(val) ? val : [])
    } else {
      payload[spec.key] = typeof val === 'string' ? val.trim() : ''
    }
  }
  return payload as Record<string, unknown> & { version: number }
}

async function onSave() {
  clearErrors()
  const found = props.validate(form)
  Object.assign(errors, found)
  if (Object.keys(errors).length) return
  saving.value = true
  saveError.value = ''
  const snapshot = captureSnapshot()
  try {
    const updated = await props.save(props.item.id, buildPayload())
    markSaved(snapshot)
    editing.value = false
    emit('updated', updated)
    ElMessage.success('标签保存成功')
  } catch (error) {
    if (isStaleConflict(error)) {
      markShown(error)
      saveError.value = '该记录已被其他人修改，请先刷新核对最新内容后再保存。'
    } else {
      saveError.value = errorMessage(error, '保存标签失败')
    }
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

function setFieldValue(key: string, val: string | string[] | null) {
  form[key] = multiKeySet.value.has(key) ? (Array.isArray(val) ? val : []) : (typeof val === 'string' ? val : '')
  delete errors[key]
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
                :model-value="(form[spec.key] as string[]) ?? []"
                multiple
                filterable
                :placeholder="spec.placeholder || '请选择'"
                @update:model-value="setFieldValue(spec.key, $event)"
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
                :model-value="(form[spec.key] as string) ?? ''"
                filterable
                :allow-create="spec.allowCreate"
                :default-first-option="spec.allowCreate"
                :clearable="spec.clearable !== false"
                :placeholder="spec.placeholder || '请选择'"
                @update:model-value="setFieldValue(spec.key, $event)"
              >
                <el-option
                  v-for="opt in spec.options"
                  :key="opt"
                  :label="opt"
                  :value="opt"
                />
              </el-select>
              <el-date-picker
                v-else-if="spec.kind === 'date'"
                :model-value="(form[spec.key] as string) ?? ''"
                type="date"
                value-format="YYYY-MM-DD"
                :placeholder="spec.placeholder || '选择日期'"
                class="review__date-picker"
                @update:model-value="setFieldValue(spec.key, $event)"
              />
              <el-input
                v-else-if="spec.kind === 'textarea'"
                :model-value="(form[spec.key] as string) ?? ''"
                type="textarea"
                :rows="spec.rows ?? 3"
                :maxlength="spec.maxlength"
                :show-word-limit="Boolean(spec.maxlength)"
                :placeholder="spec.placeholder"
                @update:model-value="setFieldValue(spec.key, $event)"
              />
              <el-input
                v-else
                :model-value="(form[spec.key] as string) ?? ''"
                :maxlength="spec.maxlength"
                :placeholder="spec.placeholder"
                @update:model-value="setFieldValue(spec.key, $event)"
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
            :row="rowForDisplay"
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
        <el-button
          :disabled="saving"
          @click="cancelEdit"
        >
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
.review__date-picker { width: 100%; }
.review__edit-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 20px; border-top: 1px solid var(--zt-border); background: var(--zt-soft); }
.review__dirty { font-size: 13px; color: var(--zt-ink-700); }
.review__edit-actions { margin-left: auto; display: flex; gap: 8px; }
@media (max-width: 767px) {
  .review__editor-grid { grid-template-columns: 1fr; }
}
</style>
