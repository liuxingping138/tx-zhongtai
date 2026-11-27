<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance } from 'element-plus'

import { copyRole, createRole, updateRole } from '@/api/system'
import { errorMessage, isStaleConflict, markShown } from '@/api/errors'
import type { RoleItem } from '@/api/types'
import { useFieldValidation } from '@/composables/useFieldValidation'
import { useUnsavedForm } from '@/composables/useUnsavedForm'

export type RoleFormMode = 'create' | 'edit' | 'copy'

const props = defineProps<{ mode: RoleFormMode; role: RoleItem | null }>()
const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ saved: [role: RoleItem, mode: RoleFormMode] }>()

const form = reactive({ name: '', description: '', code: '' })
const formRef = ref<FormInstance>()
const saving = ref(false)
const submitError = ref('')
const showCode = ref(false)
const validation = useFieldValidation(form, formRef)
const guard = useUnsavedForm(visible, () => form, saving)

const title = computed(() => ({ create: '新增角色', edit: '编辑角色', copy: '复制角色' })[props.mode])
const submitText = computed(() => ({ create: '创建', edit: '保存', copy: '复制' })[props.mode])

watch(visible, (open) => {
  if (!open) return
  submitError.value = ''
  showCode.value = false
  form.code = ''
  if (props.mode === 'edit' && props.role) {
    form.name = props.role.name
    form.description = props.role.description ?? ''
  } else if (props.mode === 'copy' && props.role) {
    form.name = `${props.role.name} 副本`
    form.description = props.role.description ?? ''
  } else {
    form.name = ''
    form.description = ''
  }
  guard.markSaved()
  void validation.validate({})
}, { flush: 'sync' })

/** 按模式调对应接口：编辑带版本号，复制带源角色，新建可指定编码。 */
function submitRole(name: string, description: string): Promise<RoleItem> {
  const role = props.role
  if (props.mode === 'edit' && role) return updateRole(role.id, { name, description, version: role.version })
  if (props.mode === 'copy' && role) return copyRole(role.id, { name, description })
  return createRole({ name, description, code: form.code.trim() || undefined })
}

function saveErrorText(error: unknown): string {
  if (isStaleConflict(error) && props.mode === 'edit') {
    markShown(error)
    return '角色已被他人修改，请关闭后重新打开最新内容再编辑。'
  }
  return errorMessage(error, '保存失败，请检查后重试')
}

async function onSubmit() {
  if (saving.value) return
  submitError.value = ''
  if (!await validation.validate({ name: form.name.trim() ? '' : '请填写角色名称' })) return
  saving.value = true
  try {
    const saved = await submitRole(form.name.trim(), form.description.trim())
    visible.value = false
    emit('saved', saved, props.mode)
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
    width="480px"
  >
    <p
      v-if="mode === 'copy' && role"
      class="editor-help"
    >
      新角色会带上「{{ role.name }}」的全部模块权限，不带成员。复制后可以再单独调整。
    </p>
    <p
      v-else-if="mode === 'create'"
      class="editor-help"
    >
      先起一个能看出职责的名称。创建后会直接进入「权限设置」，勾选它能用的模块。
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
        label="角色名称"
        required
        :error="validation.errors.name"
      >
        <el-input
          v-model="form.name"
          maxlength="128"
          placeholder="例如：政策数据管理员"
          :aria-invalid="Boolean(validation.errors.name)"
          aria-describedby="role-form-name-error"
        />
        <template #error>
          <p
            v-if="validation.errors.name"
            id="role-form-name-error"
            class="field-error"
            role="alert"
          >
            {{ validation.errors.name }}
          </p>
        </template>
      </el-form-item>
      <el-form-item label="职责说明">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="例如：负责政策三张表的日常维护，可导入导出数据。分配角色时，管理员据此判断该选哪个。"
        />
      </el-form-item>
      <template v-if="mode === 'create'">
        <el-button
          v-if="!showCode"
          link
          type="primary"
          class="role-form__code-toggle"
          @click="showCode = true"
        >
          自定义角色编码（选填）
        </el-button>
        <el-form-item
          v-else
          label="角色编码"
        >
          <el-input
            v-model="form.code"
            maxlength="64"
            placeholder="不填则自动生成，例如 policy_admin"
          />
          <p class="role-form__code-help">
            系统内部标识，创建后不可修改；小写字母开头，可含数字、点、下划线、短横线。
          </p>
        </el-form-item>
      </template>
    </el-form>
    <template #footer>
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
    </template>
  </el-dialog>
</template>

<style scoped>
.role-form__code-toggle { margin-top: -4px; }
.role-form__code-help { margin: 6px 0 0; font-size: 12px; line-height: 1.5; color: var(--zt-ink-500); }
</style>
