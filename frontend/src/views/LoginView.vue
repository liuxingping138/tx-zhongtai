<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'
import { errorMessage, isApiError } from '@/api/errors'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
})

async function onSubmit() {
  if (!form.username.trim() || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.signIn(form.username.trim(), form.password)
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(auth.mustChangePassword ? { name: 'change-password' } : redirect)
  } catch (error) {
    if (isApiError(error) && error.status === 429) {
      ElMessage.warning(error.message)
    } else {
      ElMessage.error(errorMessage(error, '登录失败'))
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <el-card class="login__card">
      <h1 class="login__title">
        中台管理端登录
      </h1>
      <el-form
        label-position="top"
        @submit.prevent="onSubmit"
      >
        <el-form-item
          label="用户名"
          required
        >
          <el-input
            v-model="form.username"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item
          label="密码"
          required
        >
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>
        <el-button
          type="primary"
          :loading="loading"
          native-type="submit"
          style="width: 100%"
        >
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
}

.login__card {
  width: 360px;
}

.login__title {
  margin: 0 0 16px;
  font-size: 20px;
  text-align: center;
}
</style>
