<script setup lang="ts">
import { nextTick, ref, useId, watch } from 'vue'
export interface EditorField {
  key: string
  label: string
  maxLength?: number
  required?: boolean
  long?: boolean
  hint?: string
  placeholder?: string
}
export interface EditorGroup {
  title: string
  hint: string
  fields: EditorField[]
}
const props = defineProps<{ groups: EditorGroup[]; submitError?: string }>()
const model = defineModel<Record<string, string>>({ required: true })
const root = ref<HTMLElement>()
const prefix = useId()
const errors = ref<Record<string, string>>({})
watch(() => ({ ...model.value }), (value, previous) => {
  for (const key of Object.keys(errors.value)) if (value[key] !== previous[key]) delete errors.value[key]
})
async function validate() {
  const next: Record<string, string> = {}
  for (const field of props.groups.flatMap(group => group.fields)) {
    if (field.required && !String(model.value[field.key] ?? '').trim()) next[field.key] = `请填写${field.label}`
  }
  errors.value = next
  if (Object.keys(next).length) {
    await nextTick()
    const field = root.value?.querySelector<HTMLElement>('[aria-invalid="true"]')
    field?.focus()
    field?.scrollIntoView({ block: 'nearest' })
    return false
  }
  return true
}
async function setError(key: string, message: string) {
  errors.value[key] = message
  await nextTick()
  root.value?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()
}
defineExpose({ validate, setError })
</script>

<template>
  <div
    ref="root"
    class="grouped-fields"
  >
    <el-alert
      v-if="submitError"
      :title="submitError"
      type="error"
      show-icon
      :closable="false"
      class="editor-submit-error"
    />
    <p class="editor-intro">
      按分组填写信息，带 <span>*</span> 的为必填项。
    </p>
    <fieldset
      v-for="(group, index) in groups"
      :key="group.title"
      class="editor-section"
    >
      <legend><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ group.title }}</legend>
      <p class="editor-section__hint">
        {{ group.hint }}
      </p>
      <div class="editor-section__grid">
        <el-form-item
          v-for="field in group.fields"
          :key="field.key"
          :label="field.label"
          :data-field="field.key"
          :required="field.required"
          :for="`${prefix}-${field.key}`"
          :error="errors[field.key]"
          :class="{ 'editor-field--wide': field.long }"
        >
          <el-input
            :id="`${prefix}-${field.key}`"
            v-model="model[field.key]"
            :aria-invalid="Boolean(errors[field.key])"
            resize="none"
            :maxlength="field.maxLength"
            :type="field.long ? 'textarea' : 'text'"
            :autosize="field.long ? { minRows: 3, maxRows: 8 } : undefined"
            :placeholder="field.placeholder || (field.required ? `请输入${field.label}` : '选填')"
            :aria-describedby="[errors[field.key] ? `${prefix}-error-${field.key}` : '', field.hint ? `${prefix}-help-${field.key}` : ''].filter(Boolean).join(' ') || undefined"
          />
          <template #error>
            <p
              v-if="errors[field.key]"
              :id="`${prefix}-error-${field.key}`"
              class="field-error"
              role="alert"
            >
              {{ errors[field.key] }}
            </p>
          </template>
          <p
            v-if="field.hint"
            :id="`${prefix}-help-${field.key}`"
            class="field-help"
          >
            {{ field.hint }}
          </p>
        </el-form-item>
      </div>
    </fieldset>
  </div>
</template>

<style scoped>
.editor-submit-error { margin-bottom: 20px; }
.field-error { margin: 5px 0 0; color: var(--el-color-danger); font-size: 12px; line-height: 1.5; }
.editor-intro { margin: 0 0 24px; color: var(--zt-ink-500); font-size: 12px; }
.editor-intro span { color: var(--el-color-danger); }
.editor-section { min-width: 0; margin: 0 0 26px; padding: 20px; border: 1px solid var(--zt-border); border-radius: 10px; background: #fff; }
.editor-section:last-child { margin-bottom: 0; }
.editor-section legend { padding: 0 8px; color: var(--zt-ink-900); font-size: 14px; font-weight: 650; }
.editor-section legend span { margin-right: 9px; color: #7891b3; font-size: 11px; font-weight: 500; }
.editor-section__hint { margin: -3px 0 20px; color: var(--zt-ink-500); font-size: 12px; line-height: 1.7; }
.editor-section__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px 18px; }
.editor-section :deep(.el-form-item) { margin-bottom: 0; min-width: 0; }
.editor-section :deep(.el-form-item__label) { font-size: 13px; color: var(--zt-ink-700); }
.editor-section :deep(.el-form-item__content) { align-content: flex-start; }
.editor-field--wide { grid-column: 1 / -1; }
.field-help { margin: 6px 0 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
@media (max-width: 540px) {
  .editor-section { padding: 16px; }
  .editor-section__grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
