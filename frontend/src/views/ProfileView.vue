<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, CircleCheck, Lock, Monitor, User } from '@element-plus/icons-vue'
import type { FormInstance } from 'element-plus'

import { useFieldValidation } from '@/composables/useFieldValidation'
import { useAuthStore } from '@/stores/auth'
import { useWorkspace } from '@/layouts/workspace'
import { errorMessage } from '@/api/errors'
import { passwordError } from '@/utils/passwordPolicy'
import ProfilePreferences from './profile/ProfilePreferences.vue'

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
const isActive = computed(() => auth.user?.status === 'active')
const primaryRole = computed(() => roles.value[0] || '暂无分配角色')
const totalModules = computed(() => groups.value.reduce((acc, g) => acc + g.entries.length, 0))
const ruleLenOk = computed(() => form.newPassword.length >= 8)
const ruleMixOk = computed(() => /[a-zA-Z]/.test(form.newPassword) && /\d/.test(form.newPassword))

const heroStats = computed(() => [
  { label: '授权角色', val: `${roles.value.length} 个`, sub: primaryRole.value, safe: false },
  { label: '可访问模块', val: `${totalModules.value} 项`, sub: `覆盖 ${groups.value.length} 大业务域`, safe: false },
  { label: '安全状态', val: isActive.value ? '正常受保护' : '账号已停用', sub: '强密码与会话管控', safe: isActive.value },
])

const tierVal = computed(() => (auth.user?.is_superadmin ? '超级管理员' : primaryRole.value))
const tierDesc = computed(() => (auth.user?.is_superadmin ? '拥有全平台最高管理权限' : '按角色矩阵动态授权'))
const statusVal = computed(() => (isActive.value ? '正常启用' : '已停用'))

const factItems = computed(() => [
  { label: '登录账号', val: `@${auth.user?.username || '—'}`, desc: '系统唯一登录标识', cls: 'fact-mono' },
  { label: '用户姓名', val: auth.user?.display_name || '—', desc: '操作日志实名署名', cls: '' },
  { label: '全局权限档位', val: tierVal.value, desc: tierDesc.value, cls: '' },
  {
    label: '账号状态',
    val: statusVal.value,
    desc: isActive.value ? '全平台业务模块正常通行' : '当前账号已停用，无法访问业务模块',
    cls: isActive.value ? 'is-ok' : '',
  },
])

const pwdFields = [
  { key: 'oldPassword', label: '原密码', auto: 'current-password', ph: '请输入当前登录密码' },
  { key: 'newPassword', label: '新密码', auto: 'new-password', ph: '请输入新密码（至少 8 位，含字母和数字）' },
  { key: 'confirm', label: '确认新密码', auto: 'new-password', ph: '请再次输入新密码以确认' },
] as const

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
        :icon="ArrowLeft"
        @click="goBack"
      >
        返回工作台
      </el-button>
      <span class="profile-top__tag"><el-icon><CircleCheck /></el-icon>账号安全中心 · 全链路受保护</span>
    </header>

    <section class="profile-hero">
      <div class="profile-hero__left">
        <div class="profile-hero__avatar">
          {{ initial }}<span class="profile-hero__online-dot" />
        </div>
        <div class="profile-hero__main">
          <div class="profile-hero__headline">
            <h1 class="profile-hero__name">
              {{ name }}
            </h1>
            <span class="profile-hero__badge">@{{ auth.user?.username || 'admin' }}</span>
            <span
              class="profile-status-pill"
              :class="isActive ? 'is-active' : 'is-warn'"
            >
              <span class="pill-dot" />{{ isActive ? '账号正常启用' : '账号已停用' }}
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
            <span class="profile-meta-sep" /><span class="profile-meta-text">腾信睿德 · 鲲宇数智</span>
            <span class="profile-meta-sep" /><span class="profile-meta-text">ID: {{ auth.user?.id || '—' }}</span>
          </div>
        </div>
      </div>

      <div class="profile-hero__stats">
        <div
          v-for="s in heroStats"
          :key="s.label"
          class="hero-stat"
        >
          <span class="hero-stat__label">{{ s.label }}</span>
          <strong
            class="hero-stat__val"
            :class="{ 'is-safe': s.safe }"
          >{{ s.val }}</strong>
          <small class="hero-stat__sub">{{ s.sub }}</small>
        </div>
      </div>
    </section>

    <div class="profile-grid">
      <div class="profile-col">
        <section class="profile-card">
          <div class="card-head">
            <span class="card-head__badge"><el-icon><User /></el-icon></span>
            <div class="card-head__text">
              <h2>账号基本档案</h2>
              <span class="card-head__sub">系统实名认证与全局 RBAC 权限配置</span>
            </div>
          </div>
          <div class="fact-grid">
            <div
              v-for="f in factItems"
              :key="f.label"
              class="fact-tile"
            >
              <span class="fact-label">{{ f.label }}</span>
              <strong
                class="fact-value"
                :class="f.cls"
              >{{ f.val }}</strong>
              <small class="fact-desc">{{ f.desc }}</small>
            </div>
          </div>
          <p class="card-hint">
            提示：登录账号与角色归属由系统管理员统一指派，所有写操作均自动关联审计轨迹。
          </p>
        </section>

        <ProfilePreferences />

        <section class="profile-card is-grow">
          <div class="card-head">
            <span class="card-head__badge"><el-icon><Monitor /></el-icon></span>
            <div class="card-head__text">
              <h2>当前账号可访问业务模块</h2>
              <span class="card-head__sub">点击任意模块胶囊可快速跳转至对应工作台</span>
            </div>
          </div>
          <div class="module-group-list">
            <div
              v-for="g in groups"
              :key="g.key"
              class="module-group"
            >
              <div class="module-group__head">
                <el-icon class="group-icon">
                  <component :is="g.icon" />
                </el-icon>
                <span class="group-title">{{ g.title }}</span>
                <span class="group-cnt">{{ g.entries.length }} 个子模块</span>
              </div>
              <div class="module-chips">
                <router-link
                  v-for="e in g.entries"
                  :key="e.path"
                  :to="e.path"
                  class="module-chip"
                >
                  <el-icon><component :is="e.icon" /></el-icon><span>{{ e.title }}</span>
                </router-link>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="profile-col">
        <section class="profile-card">
          <div class="card-head">
            <span class="card-head__badge"><el-icon><Lock /></el-icon></span>
            <div class="card-head__text">
              <h2>修改登录密码</h2>
              <span class="card-head__sub">定期更换高强度密码保障账号与业务数据安全</span>
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
            <template
              v-for="pf in pwdFields"
              :key="pf.key"
            >
              <el-form-item
                :label="pf.label"
                :error="errors[pf.key]"
                required
              >
                <el-input
                  v-model="form[pf.key]"
                  type="password"
                  show-password
                  :autocomplete="pf.auto"
                  :placeholder="pf.ph"
                />
              </el-form-item>
              <div
                v-if="pf.key === 'newPassword'"
                class="pwd-rules"
              >
                <span
                  class="pwd-rule-pill"
                  :class="{ 'is-met': ruleLenOk }"
                >✓ 长度至少 8 位字符</span>
                <span
                  class="pwd-rule-pill"
                  :class="{ 'is-met': ruleMixOk }"
                >✓ 包含英文字母与数字</span>
              </div>
            </template>
            <div class="pwd-actions">
              <el-button
                type="primary"
                :loading="loading"
                native-type="submit"
              >
                保存新密码
              </el-button>
            </div>
          </el-form>
        </section>

        <section class="profile-card is-grow">
          <div class="card-head">
            <span class="card-head__badge"><el-icon><Monitor /></el-icon></span>
            <div class="card-head__text">
              <h2>登录设备与安全会话</h2>
              <span class="card-head__sub">管理此账号在全部终端上的活动连接状态</span>
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
            若怀疑账号被他人异地使用或公共设备未退出，可一键结束此账号的所有历史登录会话。
          </p>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-view { max-width: 1240px; margin: 0 auto; display: flex; flex-direction: column; gap: 18px; }
.profile-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.profile-top__tag { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px; font-size: 12px; font-weight: 550; color: var(--zt-success-text); background: var(--zt-success-soft); border: 1px solid var(--zt-success-border); }
.profile-hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 24px 28px; background: var(--zt-hero-gradient); border: 1px solid var(--el-color-primary-light-7); border-radius: 14px; box-shadow: var(--zt-shadow); }
.profile-hero__left { display: flex; align-items: center; gap: 20px; min-width: 0; flex: 1; }
.profile-hero__avatar { position: relative; display: grid; place-items: center; flex: 0 0 64px; width: 64px; height: 64px; border-radius: 50%; background: var(--zt-avatar-gradient); color: var(--el-color-white); font-size: 26px; font-weight: 650; box-shadow: var(--zt-avatar-ring); }
.profile-hero__online-dot { position: absolute; right: 1px; bottom: 1px; width: 14px; height: 14px; border-radius: 50%; background: var(--zt-success); border: 2.5px solid var(--zt-panel); }
.profile-hero__main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 8px; }
.profile-hero__headline, .profile-hero__meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 12.5px; color: var(--zt-ink-500); }
.profile-hero__name { margin: 0; font-size: 22px; font-weight: 650; color: var(--zt-ink-900); letter-spacing: -0.01em; }
.profile-hero__badge { font-family: monospace; font-size: 12.5px; color: var(--zt-ink-700); background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 6px; padding: 1px 8px; }
.profile-meta-sep { width: 3px; height: 3px; border-radius: 50%; background: var(--zt-border-strong); }
.profile-role-chip { padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; background: var(--el-color-primary-light-9); color: var(--zt-blue-600); border: 1px solid var(--el-color-primary-light-7); }
.profile-role-chip.is-muted, .pwd-rule-pill { padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 500; color: var(--zt-ink-500); background: var(--zt-surface-subtle); border: 1px solid var(--zt-border); }
.profile-status-pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.profile-status-pill.is-active, .pwd-rule-pill.is-met { background: var(--zt-success-soft); color: var(--zt-success-text); border: 1px solid var(--zt-success-border); }
.profile-status-pill.is-warn { background: var(--zt-warning-soft); color: var(--zt-warning-text); border: 1px solid var(--zt-warning-border); }
.pill-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.profile-hero__stats { display: flex; align-items: stretch; gap: 12px; flex-shrink: 0; }
.hero-stat { display: flex; flex-direction: column; gap: 2px; min-width: 124px; padding: 10px 16px; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 10px; box-shadow: var(--zt-shadow); }
.hero-stat__label, .hero-stat__sub, .fact-desc { font-size: 11.5px; color: var(--zt-ink-500); }
.hero-stat__val { font-size: 17px; font-weight: 650; color: var(--zt-ink-900); }
.hero-stat__val.is-safe, .fact-value.is-ok { color: var(--zt-success-text); }
.profile-grid { display: grid; grid-template-columns: 1fr 1fr; align-items: stretch; gap: 20px; }
.profile-col { display: flex; flex-direction: column; gap: 20px; }
.profile-card { padding: 22px 24px; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 12px; box-shadow: var(--zt-shadow); display: flex; flex-direction: column; gap: 16px; }
.profile-card.is-grow { flex: 1; }
.card-head { display: flex; align-items: center; gap: 12px; padding-bottom: 14px; border-bottom: 1px solid var(--zt-divider); }
.card-head__badge { display: grid; place-items: center; flex: 0 0 38px; width: 38px; height: 38px; border-radius: 10px; background: var(--zt-card-icon-bg); color: var(--zt-blue-600); font-size: 18px; }
.card-head h2 { margin: 0; font-size: 15.5px; font-weight: 650; color: var(--zt-ink-900); line-height: 1.3; }
.card-head__text, .module-group-list, .pwd-form { display: flex; flex-direction: column; gap: 10px; }
.card-head__text { gap: 2px; }
.card-head__sub, .fact-label, .session-indicator p, .session-desc { font-size: 12px; color: var(--zt-ink-500); margin: 0; }
.fact-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.fact-tile, .module-group { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; background: var(--zt-surface-subtle); border: 1px solid var(--zt-border); border-radius: 10px; }
.fact-value { font-size: 14.5px; font-weight: 650; color: var(--zt-ink-900); }
.fact-mono { font-family: monospace; }
.card-hint { margin: 0; padding: 10px 12px; border-radius: 8px; background: var(--zt-soft); font-size: 12px; line-height: 1.5; color: var(--zt-ink-500); }
.module-group__head, .session-indicator { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 600; color: var(--zt-ink-900); }
.group-icon, .module-chip .el-icon { color: var(--zt-blue-600); font-size: 14px; }
.group-cnt { margin-left: auto; font-size: 11.5px; font-weight: 500; color: var(--zt-ink-500); background: var(--zt-panel); padding: 1px 8px; border-radius: 999px; border: 1px solid var(--zt-border); }
.module-chips, .pwd-rules { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
.module-chip { display: inline-flex; align-items: center; gap: 5px; padding: 4px 11px; border-radius: 8px; font-size: 12.5px; font-weight: 500; color: var(--zt-ink-700); background: var(--zt-panel); border: 1px solid var(--zt-border-strong); box-shadow: var(--zt-btn-sec-shadow); transition: all 0.15s ease; }
.module-chip:hover { color: var(--zt-blue-600); border-color: var(--zt-blue-600); transform: translateY(-1px); }
.pwd-alert, .pwd-form :deep(.el-form-item) { margin-bottom: 0; }
.pwd-actions { margin-top: 6px; }
.session-status-box { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; background: var(--zt-surface-subtle); border: 1px solid var(--zt-border); border-radius: 10px; }
.session-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--zt-success); box-shadow: 0 0 0 3px var(--zt-success-soft); }
.session-indicator strong { display: block; font-size: 13.5px; color: var(--zt-ink-900); margin-bottom: 2px; }
@media (max-width: 1024px) {
  .profile-grid { grid-template-columns: 1fr; }
  .profile-hero__stats { width: 100%; flex-wrap: wrap; }
  .profile-hero { flex-direction: column; align-items: flex-start; }
}
</style>
