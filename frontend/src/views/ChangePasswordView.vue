<script setup lang="ts">
import { reactive, ref } from 'vue'
import { passwordError } from '@/utils/passwordPolicy'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import type { FormInstance } from 'element-plus'
import { useFieldValidation } from '@/composables/useFieldValidation'
import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/api/errors'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const form = reactive({
  oldPassword: '',
  newPassword: '',
  confirm: '',
})

const formRef = ref<FormInstance>()
const saveError = ref('')
const { errors, validate } = useFieldValidation(form, formRef)

async function onSubmit() {
  if (loading.value) return
  saveError.value = ''
  if (!await validate({
    oldPassword: form.oldPassword ? '' : '请填写原密码',
    newPassword: passwordError(form.newPassword),
    confirm: form.confirm && form.confirm === form.newPassword ? '' : '两次输入的新密码不一致',
  })) return
  loading.value = true
  try {
    await auth.updatePassword(form.oldPassword, form.newPassword)
    ElMessage.success('密码已更新')
    await router.replace({ name: 'home' })
  } catch (error) {
    saveError.value = errorMessage(error, '修改密码失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="change-password">
    <el-card class="change-password__card">
      <h1>首次登录请修改密码</h1>
      <p>当前账号必须修改初始密码后才能使用系统。</p>
      <el-alert
        v-if="saveError"
        :title="saveError"
        type="error"
        show-icon
        :closable="false"
      />
      <el-form
        ref="formRef"
        novalidate
        label-position="top"
        @submit.prevent="onSubmit"
      >
        <el-form-item
          label="原密码"
          :error="errors.oldPassword"
          for="password-oldPassword"
          required
        >
          <el-input
            id="password-oldPassword"
            v-model="form.oldPassword"
            autocomplete="current-password"
            :aria-invalid="Boolean(errors.oldPassword)"
            :aria-describedby="errors.oldPassword ? 'password-oldPassword-error' : undefined"
            type="password"
            show-password
          />
          <template #error="{ error }">
            <span
              id="password-oldPassword-error"
              class="field-error"
              role="alert"
            >{{ error }}</span>
          </template>
        </el-form-item>
        <el-form-item
          label="新密码"
          :error="errors.newPassword"
          for="password-newPassword"
          required
        >
          <el-input
            id="password-newPassword"
            v-model="form.newPassword"
            autocomplete="new-password"
            :aria-invalid="Boolean(errors.newPassword)"
            :aria-describedby="errors.newPassword ? 'password-newPassword-error' : undefined"
            type="password"
            show-password
          />
          <template #error="{ error }">
            <span
              id="password-newPassword-error"
              class="field-error"
              role="alert"
            >{{ error }}</span>
          </template>
        </el-form-item>
        <el-form-item
          label="确认新密码"
          :error="errors.confirm"
          for="password-confirm"
          required
        >
          <el-input
            id="password-confirm"
            v-model="form.confirm"
            autocomplete="new-password"
            :aria-invalid="Boolean(errors.confirm)"
            :aria-describedby="errors.confirm ? 'password-confirm-error' : undefined"
            type="password"
            show-password
          />
          <template #error="{ error }">
            <span
              id="password-confirm-error"
              class="field-error"
              role="alert"
            >{{ error }}</span>
          </template>
        </el-form-item>
        <el-button
          type="primary"
          :loading="loading"
          native-type="submit"
        >
          保存并进入系统
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.change-password {
  min-height: 100dvh;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.change-password__card {
  width: min(420px, calc(100vw - 32px));
}
</style>
