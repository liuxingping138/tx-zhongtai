<script setup lang="ts">
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
defineProps<{ groups: EditorGroup[] }>()
const model = defineModel<Record<string, string>>({ required: true })
</script>

<template>
  <div class="grouped-fields">
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
          :class="{ 'editor-field--wide': field.long }"
        >
          <el-input
            v-model="model[field.key]"
            :maxlength="field.maxLength"
            :type="field.long ? 'textarea' : 'text'"
            :autosize="field.long ? { minRows: 3, maxRows: 8 } : undefined"
            :placeholder="field.placeholder || (field.required ? `请输入${field.label}` : '选填')"
            :aria-describedby="field.hint ? `field-help-${field.key}` : undefined"
          />
          <p
            v-if="field.hint"
            :id="`field-help-${field.key}`"
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
