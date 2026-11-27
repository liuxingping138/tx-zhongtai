<script setup lang="ts">
import { ElMessage, type FormInstance } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import {
  createThinktankDict,
  updateThinktankDict,
  type ThinktankDictItem,
  type ThinktankDictSlug,
} from '@/api/codebook'
import { errorMessage, isStaleConflict, markShown } from '@/api/errors'
import { useFieldValidation } from '@/composables/useFieldValidation'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import type { ThinktankDictConfig } from './configs'

const props = defineProps<{
  slug: ThinktankDictSlug
  config: ThinktankDictConfig
  item: ThinktankDictItem | null
}>()

const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ saved: [item: ThinktankDictItem, mode: 'create' | 'edit'] }>()

const form = reactive({ name: '' })
const formRef = ref<FormInstance>()
const saving = ref(false)
const submitError = ref('')
const validation = useFieldValidation(form, formRef)
const guard = useUnsavedForm(visible, () => form, saving)

const isEdit = computed(() => props.item !== null)
const title = computed(() => `${isEdit.value ? '编辑' : '新增'}${props.config.fieldLabel}`)
const submitText = computed(() => (isEdit.value ? '保存' : '创建'))

watch(visible, (open) => {
  if (!open) return
  submitError.value = ''
  form.name = props.item ? props.item.name : ''
  void validation.validate({})
  guard.markSaved()
})

function saveErrorText(error: unknown): string {
  if (isStaleConflict(error) && props.item) {
    markShown(error)
    return `${props.config.fieldLabel}已被他人修改，请关闭后刷新列表再编辑。`
  }
  return errorMessage(error, '保存失败，请检查后重试')
}

async function onSubmit(): Promise<void> {
  if (saving.value) return
  submitError.value = ''
  const trimmed = form.name.trim()
  if (!await validation.validate({ name: trimmed ? '' : `请填写${props.config.fieldLabel}` })) return
  saving.value = true
  try {
    const mode = props.item ? 'edit' : 'create'
    const saved = props.item
      ? await updateThinktankDict(props.slug, props.item.id, { name: trimmed, version: props.item.version })
      : await createThinktankDict(props.slug, { name: trimmed })
    guard.markSaved()
    visible.value = false
    ElMessage.success(mode === 'edit' ? '已保存' : '已新增')
    emit('saved', saved, mode)
  } catch (error) {
    submitError.value = saveErrorText(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    class="editor-overlay"
    :before-close="guard.beforeClose"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    :title="title"
    width="460px"
  >
    <p class="editor-help">
      {{ config.hint }}
    </p>
    <el-form
      ref="formRef"
      novalidate
      :disabled="saving"
      label-position="top"
      @submit.prevent="onSubmit"
    >
      <el-alert
        v-if="submitError"
        :title="submitError"
        type="error"
        show-icon
        :closable="false"
        class="form-submit-error"
      />
      <el-form-item
        :label="config.fieldLabel"
        required
        :error="validation.errors.name"
      >
        <el-input
          v-model="form.name"
          maxlength="128"
          show-word-limit
          :placeholder="`请输入${config.fieldLabel}`"
          :aria-invalid="Boolean(validation.errors.name)"
          aria-describedby="thinktank-dict-name-error"
        />
        <template #error>
          <p
            v-if="validation.errors.name"
            id="thinktank-dict-name-error"
            class="field-error"
            role="alert"
          >
            {{ validation.errors.name }}
          </p>
        </template>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dict-dialog-footer">
        <span
          v-if="guard.dirty.value"
          class="editor-dirty"
          role="status"
        >有未保存的修改</span>
        <el-button
          :disabled="saving"
          @click="guard.close"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="onSubmit"
        >
          {{ submitText }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.dict-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}
</style>
