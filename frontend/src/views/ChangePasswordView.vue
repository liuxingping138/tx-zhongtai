<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

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

async function onSubmit() {
  if (!form.oldPassword || !form.newPassword) {
    ElMessage.warning('请填写原密码和新密码')
    return
  }
  if (form.newPassword.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  if (form.newPassword !== form.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  loading.value = true
  try {
    await auth.updatePassword(form.oldPassword, form.newPassword)
    ElMessage.success('密码已更新')
    await router.replace({ name: 'home' })
  } catch (error) {
    ElMessage.error(errorMessage(error, '修改密码失败'))
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
      <el-form
        label-position="top"
        @submit.prevent="onSubmit"
      >
        <el-form-item
          label="原密码"
          required
        >
          <el-input
            v-model="form.oldPassword"
            type="password"
            show-password
          />
        </el-form-item>
        <el-form-item
          label="新密码"
          required
        >
          <el-input
            v-model="form.newPassword"
            type="password"
            show-password
          />
        </el-form-item>
        <el-form-item
          label="确认新密码"
          required
        >
          <el-input
            v-model="form.confirm"
            type="password"
            show-password
          />
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
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.change-password__card {
  width: 420px;
}
</style>
