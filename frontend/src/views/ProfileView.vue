<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

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

async function onChangePassword() {
  if (loading.value) return
  saveError.value = ''
  if (!await validate({
    oldPassword: form.oldPassword ? '' : '请填写原密码',
    newPassword: form.newPassword.length >= 8 ? '' : '新密码至少 8 位',
    confirm: form.confirm && form.confirm === form.newPassword ? '' : '两次输入的新密码不一致',
  })) return
  loading.value = true
  try {
    await auth.updatePassword(form.oldPassword, form.newPassword)
    form.oldPassword = ''
    form.newPassword = ''
    form.confirm = ''
    ElMessage.success('密码已修改')
  } catch (error) {
    saveError.value = errorMessage(error, '修改密码失败')
  } finally {
    loading.value = false
  }
}

function goBack() {
  const state = window.history.state as { back?: unknown }
  if (state?.back) {
    router.back()
    return
  }
  void router.push({ name: 'home' })
}

async function onLogoutAll() {
  await ElMessageBox.confirm('将退出你在全部设备上的登录，是否继续？', '退出全部设备', { type: 'warning' })
  try {
    const revoked = await auth.signOutAll()
    ElMessage.success(`已撤销 ${revoked} 个会话`)
    await router.push({ name: 'login' })
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(errorMessage(error, '操作失败'))
    }
  }
}
</script>

<template>
  <el-card>
    <el-page-header
      class="profile__header"
      title="返回"
      content="个人设置"
      @back="goBack"
    />
    <el-descriptions
      :column="1"
      border
    >
      <el-descriptions-item label="用户名">
        {{ auth.user?.username }}
      </el-descriptions-item>
      <el-descriptions-item label="显示名">
        {{ auth.user?.display_name }}
      </el-descriptions-item>
      <el-descriptions-item label="角色">
        {{ auth.user?.roles?.length ? auth.user.roles.join('、') : '未分配角色' }}
      </el-descriptions-item>
      <el-descriptions-item label="状态">
        {{ auth.user?.status }}
      </el-descriptions-item>
    </el-descriptions>
    <h3>修改密码</h3>
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
      style="max-width: 420px"
      @submit.prevent="onChangePassword"
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
      <el-form-item>
        <el-button
          type="primary"
          :loading="loading"
          native-type="submit"
        >
          保存密码
        </el-button>
        <el-button @click="onLogoutAll">
          退出全部设备
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.profile__header {
  margin-bottom: 16px;
}
</style>
