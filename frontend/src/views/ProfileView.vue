<script setup lang="ts">
import { reactive, ref } from 'vue'
import { passwordError } from '@/utils/passwordPolicy'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'

import type { FormInstance } from 'element-plus'
import { useFieldValidation } from '@/composables/useFieldValidation'
import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/api/errors'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const revoking = ref(false)
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
    newPassword: passwordError(form.newPassword),
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
  if (revoking.value) return
  const confirmed = await ElMessageBox.confirm(
    '这会立即撤销此账号在全部设备上的登录，需要重新输入密码登录。',
    '退出全部设备？',
    { type: 'warning', confirmButtonText: '退出全部设备', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!confirmed) return
  revoking.value = true
  try {
    const revoked = await auth.signOutAll()
    ElMessage.success(`已撤销 ${revoked} 个会话`)
    await router.push({ name: 'login' })
  } catch (error) {
    ElMessage.error(errorMessage(error, '退出全部设备失败'))
  } finally {
    revoking.value = false
  }
}

const STATUS_TEXT: Record<string, string> = { active: '启用', disabled: '停用' }
</script>

<template>
  <div class="profile">
    <header class="profile__heading">
      <el-button
        link
        :icon="ArrowLeft"
        @click="goBack"
      >
        返回
      </el-button>
      <h1>个人设置</h1>
      <p>查看账号信息，管理密码和登录设备。</p>
    </header>

    <div class="profile__grid">
      <section
        class="profile__panel profile__identity"
        aria-labelledby="profile-account-title"
      >
        <h2 id="profile-account-title">
          账号信息
        </h2>
        <div class="profile__person">
          <span
            class="profile__avatar"
            aria-hidden="true"
          >{{ auth.user?.display_name?.slice(0, 1) || '用' }}</span>
          <div>
            <strong>{{ auth.user?.display_name || auth.user?.username || '当前用户' }}</strong>
            <span>{{ auth.user?.username || '—' }}</span>
          </div>
        </div>
        <dl class="profile__facts">
          <div>
            <dt>账号状态</dt>
            <dd>
              <el-tag
                size="small"
                :type="auth.user?.status === 'active' ? 'success' : 'warning'"
              >
                {{ STATUS_TEXT[auth.user?.status || ''] || auth.user?.status || '—' }}
              </el-tag>
            </dd>
          </div>
          <div>
            <dt>已分配角色</dt>
            <dd class="profile__roles">
              <el-tag
                v-for="role in auth.user?.roles || []"
                :key="role"
                size="small"
                effect="plain"
              >
                {{ role }}
              </el-tag>
              <span
                v-if="!auth.user?.roles?.length"
                class="profile__muted"
              >未分配角色</span>
            </dd>
          </div>
        </dl>
        <p class="profile__note">
          账号和角色由管理员统一配置。
        </p>
      </section>

      <section
        class="profile__panel profile__security"
        aria-labelledby="profile-security-title"
      >
        <div class="profile__section-head">
          <h2 id="profile-security-title">
            修改密码
          </h2>
          <p>下次登录请使用新密码。</p>
        </div>
        <el-alert
          v-if="saveError"
          class="profile__error"
          :title="saveError"
          type="error"
          show-icon
          :closable="false"
        />
        <el-form
          ref="formRef"
          class="profile__form"
          novalidate
          label-position="top"
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
              :aria-describedby="errors.newPassword ? 'password-newPassword-error password-newPassword-hint' : 'password-newPassword-hint'"
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
          <p
            id="password-newPassword-hint"
            class="profile__field-hint"
          >
            至少 8 位，要有字母和数字。
          </p>
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
          <el-form-item class="profile__save">
            <el-button
              type="primary"
              :loading="loading"
              native-type="submit"
            >
              保存密码
            </el-button>
          </el-form-item>
        </el-form>

        <div class="profile__sessions">
          <div>
            <h3>登录设备</h3>
            <p>如果怀疑账号被他人使用，可以结束此账号的全部登录会话。</p>
          </div>
          <el-button
            :loading="revoking"
            @click="onLogoutAll"
          >
            退出全部设备
          </el-button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.profile { max-width: 1160px; margin: 0 auto; }
.profile__heading { margin-bottom: 20px; }
.profile__heading .el-button { margin: 0 0 6px -4px; }
.profile__heading h1 { margin: 0; color: var(--zt-ink-900); font-size: var(--zt-title-size); line-height: 1.4; font-weight: 650; }
.profile__heading p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 13px; }
.profile__grid { display: grid; grid-template-columns: minmax(260px, 340px) minmax(0, 1fr); align-items: start; gap: 20px; }
.profile__panel { min-width: 0; padding: 24px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); }
.profile__panel h2 { margin: 0; color: var(--zt-ink-900); font-size: 17px; font-weight: 650; }
.profile__person { display: flex; align-items: center; gap: 12px; margin-top: 22px; padding-bottom: 20px; border-bottom: 1px solid var(--zt-border); }
.profile__avatar { display: grid; flex: 0 0 44px; width: 44px; height: 44px; place-items: center; border-radius: 11px; background: var(--el-color-primary-light-9); color: var(--zt-blue-800); font-size: 18px; font-weight: 650; }
.profile__person strong, .profile__person span { display: block; }
.profile__person strong { font-size: 16px; }
.profile__person div > span { margin-top: 2px; color: var(--zt-ink-500); font-size: 13px; }
.profile__facts { margin: 0; }
.profile__facts > div { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 16px 0; border-bottom: 1px solid var(--zt-border); }
.profile__facts dt { flex: 0 0 auto; color: var(--zt-ink-500); font-size: 13px; }
.profile__facts dd { margin: 0; text-align: right; }
.profile__roles { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 6px; }
.profile__muted, .profile__note { color: var(--zt-ink-500); font-size: 12px; }
.profile__note { margin: 18px 0 0; line-height: 1.6; }
.profile__section-head { margin-bottom: 20px; }
.profile__section-head p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 13px; }
.profile__error { margin-bottom: 16px; }
.profile__form { max-width: 460px; }
.profile__form :deep(.el-form-item) { margin-bottom: 16px; }
.profile__form :deep(.el-input__wrapper) { min-height: 38px; }
.profile__field-hint { margin: -10px 0 16px; color: var(--zt-ink-500); font-size: 12px; }
.profile__form :deep(.profile__save) { margin: 20px 0 0; }
.profile__sessions { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-top: 28px; padding-top: 22px; border-top: 1px solid var(--zt-border); }
.profile__sessions h3 { margin: 0; font-size: 14px; font-weight: 650; }
.profile__sessions p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
.profile__sessions .el-button { flex: 0 0 auto; }
@media (max-width: 900px) { .profile__grid { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 767px) { .profile__panel { padding: 18px; } .profile__sessions { align-items: flex-start; flex-direction: column; } }
</style>
