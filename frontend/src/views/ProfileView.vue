<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Lock, Monitor, User } from '@element-plus/icons-vue'
import type { FormInstance } from 'element-plus'

import { useFieldValidation } from '@/composables/useFieldValidation'
import { useAuthStore } from '@/stores/auth'
import { useWorkspace } from '@/layouts/workspace'
import { errorMessage } from '@/api/errors'
import { passwordError } from '@/utils/passwordPolicy'

const auth = useAuthStore()
const router = useRouter()
const { groups } = useWorkspace()

const loading = ref(false)
const revoking = ref(false)
const form = reactive({ oldPassword: '', newPassword: '', confirm: '' })
const formRef = ref<FormInstance>()
const saveError = ref('')
const { errors, validate } = useFieldValidation(form, formRef)

const name = computed(() => auth.user?.display_name || auth.user?.username || '当前用户')
const initial = computed(() => name.value.slice(0, 1))
const roles = computed(() => auth.user?.roles?.filter(Boolean) || [])

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
    ElMessage.success('密码已成功修改')
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
    '这会立即撤销此账号在全部设备上的登录会话，需重新输入密码登录。',
    '退出全部设备？',
    { type: 'warning', confirmButtonText: '退出全部设备', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!confirmed) return
  revoking.value = true
  try {
    const count = await auth.signOutAll()
    ElMessage.success(`已安全撤销 ${count} 个历史会话`)
    await router.push({ name: 'login' })
  } catch (error) {
    ElMessage.error(errorMessage(error, '退出全部设备失败'))
  } finally {
    revoking.value = false
  }
}
</script>

<template>
  <div class="profile-view">
    <header class="profile-top">
      <el-button
        link
        :icon="ArrowLeft"
        class="profile-back"
        @click="goBack"
      >
        返回控制台
      </el-button>
    </header>

    <section
      class="profile-hero"
      aria-label="账号身份概览"
    >
      <div class="profile-hero__avatar">
        {{ initial }}
      </div>
      <div class="profile-hero__main">
        <div class="profile-hero__headline">
          <h1 class="profile-hero__name">
            {{ name }}
          </h1>
          <span class="profile-hero__badge">@{{ auth.user?.username }}</span>
          <span
            class="profile-status-pill"
            :class="auth.user?.status === 'active' ? 'is-active' : 'is-warn'"
          >
            <span class="pill-dot" />{{ auth.user?.status === 'active' ? '账号正常启用' : '账号已停用' }}
          </span>
        </div>
        <div class="profile-hero__meta">
          <span
            v-for="r in roles"
            :key="r"
            class="profile-role-chip"
          >{{ r }}</span>
          <span
            v-if="!roles.length"
            class="profile-role-chip is-muted"
          >未分配角色</span>
          <span class="profile-meta-sep" /><span class="profile-meta-text">腾信睿德业务中台</span>
          <span class="profile-meta-sep" /><span class="profile-meta-text">ID: {{ auth.user?.id || '—' }}</span>
        </div>
      </div>
    </section>

    <div class="profile-grid">
      <div class="profile-col">
        <section
          class="profile-card"
          aria-labelledby="card-info"
        >
          <div class="card-head">
            <el-icon class="card-head__icon">
              <User />
            </el-icon>
            <h2 id="card-info">
              账号基本档案
            </h2>
          </div>
          <div class="fact-list">
            <div class="fact-item">
              <span class="fact-label">登录账号</span><span class="fact-value fact-mono">{{ auth.user?.username || '—' }}</span>
            </div>
            <div class="fact-item">
              <span class="fact-label">用户姓名</span><span class="fact-value">{{ auth.user?.display_name || '—' }}</span>
            </div>
            <div class="fact-item">
              <span class="fact-label">全局权限档位</span><span class="fact-value">{{ auth.user?.is_superadmin ? '超级管理员 (全局最高)' : '标准业务角色' }}</span>
            </div>
            <div class="fact-item">
              <span class="fact-label">账号状态</span><span class="fact-value">{{ auth.user?.status === 'active' ? '正常启用' : '已停用' }}</span>
            </div>
          </div>
          <p class="card-hint">
            提示：登录账号、角色归属由系统管理员统一指派与配置。
          </p>
        </section>

        <section
          class="profile-card"
          aria-labelledby="card-modules"
        >
          <div class="card-head">
            <el-icon class="card-head__icon">
              <Monitor />
            </el-icon>
            <h2 id="card-modules">
              当前账号可访问业务模块
            </h2>
          </div>
          <div class="module-group-list">
            <div
              v-for="g in groups"
              :key="g.key"
              class="module-group"
            >
              <div class="module-group__head">
                <span class="group-dot" /><span class="group-title">{{ g.title }}</span><span class="group-cnt">{{ g.entries.length }} 个子模块</span>
              </div>
              <div class="module-chips">
                <span
                  v-for="e in g.entries"
                  :key="e.path"
                  class="module-chip"
                >{{ e.title }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="profile-col">
        <section
          class="profile-card"
          aria-labelledby="card-pwd"
        >
          <div class="card-head">
            <el-icon class="card-head__icon">
              <Lock />
            </el-icon>
            <div class="card-head__text">
              <h2 id="card-pwd">
                修改登录密码
              </h2>
              <span class="card-head__sub">定期更换强密码保障账号安全</span>
            </div>
          </div>

          <el-alert
            v-if="saveError"
            class="pwd-alert"
            :title="saveError"
            type="error"
            show-icon
            :closable="false"
          />

          <el-form
            ref="formRef"
            class="pwd-form"
            novalidate
            label-position="top"
            @submit.prevent="onChangePassword"
          >
            <el-form-item
              label="原密码"
              :error="errors.oldPassword"
              required
            >
              <el-input
                v-model="form.oldPassword"
                type="password"
                show-password
                autocomplete="current-password"
                placeholder="请输入当前密码"
              />
            </el-form-item>
            <el-form-item
              label="新密码"
              :error="errors.newPassword"
              required
            >
              <el-input
                v-model="form.newPassword"
                type="password"
                show-password
                autocomplete="new-password"
                placeholder="请输入新密码（至少 8 位，含字母和数字）"
              />
            </el-form-item>
            <div class="pwd-rules">
              <span class="pwd-rule-item">✓ 长度至少 8 位</span><span class="pwd-rule-item">✓ 必须包含英文字母与数字</span>
            </div>
            <el-form-item
              label="确认新密码"
              :error="errors.confirm"
              required
            >
              <el-input
                v-model="form.confirm"
                type="password"
                show-password
                autocomplete="new-password"
                placeholder="请再次输入新密码"
              />
            </el-form-item>
            <div class="pwd-actions">
              <el-button
                type="primary"
                :loading="loading"
                native-type="submit"
                class="pwd-submit"
              >
                保存新密码
              </el-button>
            </div>
          </el-form>
        </section>

        <section
          class="profile-card"
          aria-labelledby="card-session"
        >
          <div class="card-head">
            <el-icon class="card-head__icon">
              <Monitor />
            </el-icon>
            <div class="card-head__text">
              <h2 id="card-session">
                登录设备与安全会话
              </h2>
              <span class="card-head__sub">管理该账号在所有终端的活动连接</span>
            </div>
          </div>
          <div class="session-status-box">
            <div class="session-indicator">
              <span class="session-dot is-online" />
              <div>
                <strong>当前设备：Web 浏览器</strong>
                <p>安全会话活跃 · HTTPS 加密通道传输</p>
              </div>
            </div>
            <el-button
              :loading="revoking"
              @click="onLogoutAll"
            >
              退出全部设备
            </el-button>
          </div>
          <p class="session-desc">
            若怀疑账号被他人异地使用或公共设备未退出，可一键结束此账号的所有历史会话。
          </p>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-view { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }
.profile-top { display: flex; align-items: center; justify-content: space-between; }
.profile-back { font-size: 13.5px; font-weight: 500; color: var(--zt-ink-700); padding: 0; }
.profile-back:hover { color: var(--zt-blue-600); }

.profile-hero {
  display: flex; align-items: center; gap: 20px; padding: 22px 28px;
  background: var(--zt-panel); border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius); box-shadow: var(--zt-shadow);
}
.profile-hero__avatar {
  display: grid; place-items: center; flex: 0 0 60px; width: 60px; height: 60px;
  border-radius: 50%; background: var(--el-color-primary-light-9); color: var(--zt-blue-600);
  font-size: 24px; font-weight: 650; box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
}
.profile-hero__main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6px; }
.profile-hero__headline { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.profile-hero__name { margin: 0; font-size: 20px; font-weight: 650; color: var(--zt-ink-900); }
.profile-hero__badge { font-family: var(--zt-font-mono, monospace); font-size: 13px; color: var(--zt-ink-500); }
.profile-hero__meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 12.5px; color: var(--zt-ink-500); }
.profile-meta-sep { width: 3px; height: 3px; border-radius: 50%; background: var(--zt-border-strong); }
.profile-role-chip { padding: 1px 9px; border-radius: 12px; font-size: 11.5px; font-weight: 550; background: var(--el-color-primary-light-9); color: var(--zt-blue-600); border: 1px solid var(--el-color-primary-light-7); }
.profile-role-chip.is-muted { background: var(--zt-surface-subtle); color: var(--zt-ink-500); border-color: var(--zt-border); }

.profile-status-pill { display: inline-flex; align-items: center; gap: 5px; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.profile-status-pill.is-active { background: var(--zt-success-soft); color: var(--zt-success-text); border: 1px solid var(--zt-success-border); }
.profile-status-pill.is-warn { background: var(--zt-warning-soft); color: var(--zt-warning-text); border: 1px solid var(--zt-warning-border); }
.pill-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

.profile-grid { display: grid; grid-template-columns: minmax(360px, 460px) minmax(0, 1fr); align-items: start; gap: 20px; }
.profile-col { display: flex; flex-direction: column; gap: 20px; }
.profile-card { padding: 22px 24px; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); box-shadow: var(--zt-shadow); display: flex; flex-direction: column; gap: 16px; }

.card-head { display: flex; align-items: center; gap: 10px; padding-bottom: 12px; border-bottom: 1px solid var(--zt-divider); }
.card-head__icon { font-size: 18px; color: var(--zt-blue-600); }
.card-head h2 { margin: 0; font-size: 15.5px; font-weight: 650; color: var(--zt-ink-900); }
.card-head__text { display: flex; flex-direction: column; gap: 2px; }
.card-head__sub { font-size: 12px; color: var(--zt-ink-500); }

.fact-list { display: flex; flex-direction: column; }
.fact-item { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--zt-divider); font-size: 13px; }
.fact-item:last-child { border-bottom: 0; }
.fact-label { color: var(--zt-ink-500); }
.fact-value { font-weight: 550; color: var(--zt-ink-900); }
.fact-mono { font-family: var(--zt-font-mono, monospace); }
.card-hint { margin: 0; font-size: 12px; line-height: 1.6; color: var(--zt-ink-500); }

.module-group-list { display: flex; flex-direction: column; gap: 14px; }
.module-group__head { display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; color: var(--zt-ink-900); }
.group-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--zt-blue-600); }
.group-cnt { margin-left: auto; font-size: 11.5px; color: var(--zt-ink-500); }
.module-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; padding-left: 12px; }
.module-chip { padding: 2px 8px; border-radius: 10px; font-size: 12px; color: var(--zt-ink-700); background: var(--zt-surface-subtle); border: 1px solid var(--zt-border); }

.pwd-alert { margin-bottom: 0; }
.pwd-form { display: flex; flex-direction: column; gap: 12px; }
.pwd-form :deep(.el-form-item) { margin-bottom: 0; }
.pwd-rules { display: flex; flex-wrap: wrap; gap: 12px; font-size: 11.5px; color: var(--zt-ink-500); margin: 2px 0 6px; }
.pwd-actions { margin-top: 6px; }

.session-status-box { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 14px; background: var(--zt-surface-subtle); border: 1px solid var(--zt-border); border-radius: var(--zt-radius-sm); }
.session-indicator { display: flex; align-items: center; gap: 10px; }
.session-dot { width: 8px; height: 8px; border-radius: 50%; }
.session-dot.is-online { background: var(--zt-success); box-shadow: 0 0 0 2px var(--zt-success-soft); }
.session-indicator strong { display: block; font-size: 13px; color: var(--zt-ink-900); }
.session-indicator p { margin: 2px 0 0; font-size: 12px; color: var(--zt-ink-500); }
.session-desc { margin: 0; font-size: 12px; line-height: 1.6; color: var(--zt-ink-500); }

@media (max-width: 960px) {
  .profile-grid { grid-template-columns: 1fr; }
  .profile-hero { flex-direction: column; align-items: flex-start; }
}
</style>
