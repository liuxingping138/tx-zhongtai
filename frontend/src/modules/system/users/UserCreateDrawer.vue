<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'

import { createUser } from '@/api/system'
import { errorMessage } from '@/api/errors'
import type { RoleItem } from '@/api/types'
import { useFieldValidation } from '@/composables/useFieldValidation'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import RolePicker from './RolePicker.vue'

/** 新增用户抽屉：建人和选角色一次完成；初始密码由服务端生成，经 created 事件交给列表页只显示一次。 */
const props = defineProps<{ modelValue: boolean; roles: RoleItem[]; canGrant: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [open: boolean]
  created: [result: { username: string; temporaryPassword: string | null }]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (open: boolean) => emit('update:modelValue', open),
})
const createForm = reactive({ username: '', display_name: '', phone: '', email: '' })
const createRoles = ref<string[]>([])
const creating = ref(false)
const createError = ref('')
const createFormRef = ref<FormInstance>()
const createValidation = useFieldValidation(createForm, createFormRef)
const createGuard = useUnsavedForm(visible, () => ({ ...createForm, roles: createRoles.value }), creating)

function resetCreateForm() {
  createForm.username = ''
  createForm.display_name = ''
  createForm.phone = ''
  createForm.email = ''
  createRoles.value = []
}

watch(visible, (open) => {
  if (!open) return
  // 打开时清空上次没提交的内容，并以清空后的表单作为「未修改」基线，避免一打开就提示未保存。
  resetCreateForm()
  createGuard.markSaved()
  createError.value = ''
  void createValidation.validate({})
})

async function confirmCreateWithoutRole(): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      '没有角色的用户登录后看不到任何业务模块。可以先创建，之后在「待分配角色」里补。',
      '还没有选择角色',
      { type: 'warning', confirmButtonText: '仍然创建', cancelButtonText: '返回选择', distinguishCancelAndClose: true },
    )
    return true
  } catch {
    return false
  }
}

function validateCreate(): Promise<boolean> {
  return createValidation.validate({
    username: createForm.username.trim() ? '' : '请填写用户名',
    display_name: createForm.display_name.trim() ? '' : '请填写显示名',
  })
}

function createPayload() {
  return {
    username: createForm.username,
    display_name: createForm.display_name,
    phone: createForm.phone.trim() || undefined,
    email: createForm.email.trim() || undefined,
    role_ids: props.canGrant && createRoles.value.length ? createRoles.value : undefined,
  }
}

async function onCreate() {
  if (creating.value) return
  createError.value = ''
  if (!await validateCreate()) return
  // 不预先挂警告，只在真要创建一个「登录后什么都看不到」的账号时确认一次。
  if (props.canGrant && !createRoles.value.length && !await confirmCreateWithoutRole()) return
  creating.value = true
  try {
    const result = await createUser(createPayload())
    ElMessage.success(createRoles.value.length ? '用户已创建' : '用户已创建，已放进「待分配角色」')
    visible.value = false
    resetCreateForm()
    emit('created', { username: result.user.username, temporaryPassword: result.temporary_password ?? null })
  } catch (error) {
    createError.value = errorMessage(error, '创建失败，请检查后重试')
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <!-- 与编辑用户同为右侧抽屉：建人和选角色在一处完成。 -->
  <el-drawer
    v-model="visible"
    class="editor-overlay"
    :before-close="createGuard.beforeClose"
    :close-on-click-modal="!creating"
    :close-on-press-escape="!creating"
    :show-close="!creating"
    title="新增用户"
    size="600px"
  >
    <!-- autocomplete 必须写：否则浏览器把已保存的管理员账号填进显示名。 -->
    <el-form
      ref="createFormRef"
      novalidate
      :disabled="creating"
      label-position="top"
    >
      <el-alert
        v-if="createError"
        :title="createError"
        type="error"
        show-icon
        :closable="false"
        class="form-submit-error"
      />
      <div class="create-grid">
        <el-form-item
          :error="createValidation.errors.username"
          label="用户名"
          required
        >
          <el-input
            v-model="createForm.username"
            autocomplete="off"
            placeholder="登录用，创建后不能改"
            :aria-invalid="Boolean(createValidation.errors.username)"
            aria-describedby="createForm-username-error"
          />
          <template #error>
            <p
              v-if="createValidation.errors.username"
              id="createForm-username-error"
              class="field-error"
              role="alert"
            >
              {{ createValidation.errors.username }}
            </p>
          </template>
        </el-form-item>
        <el-form-item
          :error="createValidation.errors.display_name"
          label="显示名"
          required
        >
          <el-input
            v-model="createForm.display_name"
            autocomplete="off"
            placeholder="页面上显示的姓名"
            :aria-invalid="Boolean(createValidation.errors.display_name)"
            aria-describedby="createForm-display_name-error"
          />
          <template #error>
            <p
              v-if="createValidation.errors.display_name"
              id="createForm-display_name-error"
              class="field-error"
              role="alert"
            >
              {{ createValidation.errors.display_name }}
            </p>
          </template>
        </el-form-item>
        <el-form-item label="电话">
          <el-input
            v-model="createForm.phone"
            autocomplete="off"
            inputmode="tel"
            maxlength="32"
            placeholder="11 位手机号，选填"
          />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input
            v-model="createForm.email"
            autocomplete="off"
            inputmode="email"
            maxlength="254"
            placeholder="选填"
          />
        </el-form-item>
      </div>
      <!-- 初始密码不让手填：避免弱密码和一批人共用同一个密码，统一由系统生成、只显示一次。 -->
      <el-form-item label="初始密码">
        <p class="field-hint">
          创建后由系统生成，只显示一次，请复制发给本人；首次登录必须改成自己的密码。
        </p>
      </el-form-item>
      <el-form-item
        label="角色"
        class="create-roles"
      >
        <template v-if="canGrant">
          <RolePicker
            v-model="createRoles"
            :roles="roles"
            :disabled="creating"
          />
          <p class="field-hint">
            角色决定能用哪些模块，可多选；不确定时也可以先不选，之后在「待分配角色」里补。
          </p>
        </template>
        <template v-else>
          <p
            class="create-roles__note"
            role="note"
          >
            分配角色需要超级管理员。可以先建账号，它会出现在「待分配角色」里，超级管理员在那里能直接看到并分配。
          </p>
          <RolePicker
            v-if="roles.length"
            :model-value="[]"
            :roles="roles"
            disabled
          />
        </template>
      </el-form-item>
    </el-form>
    <template #footer>
      <span
        v-if="createGuard.dirty.value"
        class="editor-dirty"
        role="status"
      >有未保存的修改</span>
      <el-button
        :disabled="creating"
        @click="createGuard.close"
      >
        取消
      </el-button>
      <el-button
        type="primary"
        :loading="creating"
        @click="onCreate"
      >
        创建
      </el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.create-roles :deep(.el-form-item__content) {
  display: block;
}

/* 用户名、显示名都是短字段，并排放省一半高度。 */
.create-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 16px;
}

.field-hint,
.create-roles__note {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

.field-hint {
  color: var(--zt-ink-500);
}

.create-roles__note {
  color: var(--zt-ink-500);
}
</style>
