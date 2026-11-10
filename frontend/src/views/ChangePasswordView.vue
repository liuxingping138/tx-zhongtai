<script setup lang="ts">
import { reactive, ref } from 'vue'
import { Lock } from '@element-plus/icons-vue'
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
    <div class="change-password__card">
      <div class="change-password__head">
        <span class="change-password__badge">
          <el-icon><Lock /></el-icon>账号安全中心
        </span>
        <h1>首次登录请修改密码</h1>
        <p class="change-password__desc">
          {{ auth.mustChangePassword ? '当前账号必须修改初始密码后才能使用系统。' : '定期更新高强度登录密码，保障企业数据资产安全。' }}
        </p>
        <div class="change-password__rule">
          密码要求：至少 8 位字符，且同时包含字母与数字
        </div>
      </div>

      <el-alert
        v-if="saveError"
        class="change-password__alert"
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
            placeholder="请输入当前使用的原密码"
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
            placeholder="至少 8 位，包含字母与数字"
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
            placeholder="请再次输入新密码"
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

        <div class="change-password__actions">
          <el-button
            v-if="!auth.mustChangePassword"
            @click="router.back()"
          >
            返回
          </el-button>
          <el-button
            class="change-password__submit"
            type="primary"
            :loading="loading"
            native-type="submit"
          >
            保存并进入系统
          </el-button>
        </div>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.change-password {
  min-height: 100dvh;
  padding: 24px 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--zt-soft);
}
.change-password__card {
  width: min(440px, calc(100vw - 32px));
  padding: 32px 30px 28px;
  border-radius: 16px;
  border: 1px solid var(--zt-border);
  background: var(--zt-panel);
  box-shadow: 0 16px 36px var(--zt-shadow-soft), var(--zt-shadow);
}
.change-password__head {
  margin-bottom: 20px;
}
.change-password__badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
  color: var(--zt-blue-700);
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 10px;
}
.change-password__head h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--zt-ink-900);
}
.change-password__desc {
  margin: 6px 0 12px;
  font-size: 13px;
  color: var(--zt-ink-500);
  line-height: 1.6;
}
.change-password__rule {
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--zt-surface-subtle);
  border: 1px solid var(--zt-border);
  color: var(--zt-ink-700);
  font-size: 12px;
}
.change-password__alert {
  margin-bottom: 16px;
}
.change-password__actions {
  display: flex;
  gap: 10px;
  margin-top: 22px;
}
.change-password__submit {
  flex: 1;
}
</style>
