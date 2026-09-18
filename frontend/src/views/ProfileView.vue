<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

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

async function onChangePassword() {
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
    form.oldPassword = ''
    form.newPassword = ''
    form.confirm = ''
    ElMessage.success('密码已修改')
  } catch (error) {
    ElMessage.error(errorMessage(error, '修改密码失败'))
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
      :column="2"
      border
    >
      <el-descriptions-item label="用户名">
        {{ auth.user?.username }}
      </el-descriptions-item>
      <el-descriptions-item label="显示名">
        {{ auth.user?.display_name }}
      </el-descriptions-item>
      <el-descriptions-item label="状态">
        {{ auth.user?.status }}
      </el-descriptions-item>
    </el-descriptions>
    <h3>修改密码</h3>
    <el-form
      label-width="100px"
      style="max-width: 420px"
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
      <el-form-item>
        <el-button
          type="primary"
          :loading="loading"
          @click="onChangePassword"
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
