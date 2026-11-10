<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight, Coin, Connection, DataAnalysis, Document, Grid,
  Hide, Lock, OfficeBuilding, User, UserFilled, View,
} from '@element-plus/icons-vue'

import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/api/errors'

const LEFT_NODES = [
  { title: '客户管理', desc: '客群画像与归属', tone: 'is-blue', icon: User },
  { title: '招投标', desc: '商机与中标线索', tone: 'is-indigo', icon: Document },
  { title: '政策与解读', desc: 'AI 打标 · 人工核对', tone: 'is-sky', icon: OfficeBuilding },
]
const RIGHT_NODES = [
  { title: '行业场景', desc: '六级标准树联动', tone: 'is-emerald', icon: Grid, badge: '' },
  { title: '码表管理', desc: '省市区与字典基准', tone: 'is-amber', icon: Coin, badge: '' },
  { title: '爬虫监测', desc: '全国信源采集监控', tone: 'is-purple', icon: DataAnalysis, badge: '独立' },
]
const FLOW_PATHS = [
  'M 0 36 C 48 36, 56 110, 100 110', 'M 0 110 L 100 110', 'M 0 184 C 48 184, 56 110, 100 110',
  'M 200 36 C 152 36, 144 110, 100 110', 'M 200 110 L 100 110',
]

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const showPassword = ref(false)
const capsLock = ref(false)
const submitError = ref('')
const usernameInput = ref<HTMLInputElement>()
const passwordInput = ref<HTMLInputElement>()
const errors = reactive({ username: '', password: '' })
const form = reactive({ username: '', password: '' })

function clearError(field: 'username' | 'password') {
  errors[field] = ''
  submitError.value = ''
}

function checkCapsLock(event: KeyboardEvent) {
  capsLock.value = event.getModifierState('CapsLock')
}

/** 校验必填并把焦点放到第一个出错的输入框。 */
function validate(): boolean {
  errors.username = form.username.trim() ? '' : '请输入用户名'
  errors.password = form.password ? '' : '请输入密码'
  if (errors.username) usernameInput.value?.focus()
  else if (errors.password) passwordInput.value?.focus()
  return !errors.username && !errors.password
}

/** 只接受站内路径；`//host` 会被浏览器当成外站地址。 */
function redirectTarget(): string {
  const target = route.query.redirect
  return typeof target === 'string' && target.startsWith('/') && !target.startsWith('//') ? target : '/'
}

async function onSubmit() {
  if (loading.value || !validate()) return
  submitError.value = ''
  loading.value = true
  try {
    await auth.signIn(form.username.trim(), form.password)
    await router.replace(auth.mustChangePassword ? { name: 'change-password' } : redirectTarget())
  } catch (error) {
    submitError.value = errorMessage(error, '登录失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login">
    <section
      class="login-story"
      aria-labelledby="platform-title"
    >
      <header class="login-brand-bar">
        <div class="login-brand">
          <span
            class="brand-mark"
            aria-hidden="true"
          ><i /><i /><i /></span>
          <div class="brand-text">
            <span class="brand-title">业务数据运营平台</span>
            <span class="brand-sub">TELELANDS DATA WORKSPACE</span>
          </div>
        </div>
        <span class="story-badge"><i aria-hidden="true" />全链路标准码表已同步</span>
      </header>

      <div class="story-content">
        <p class="eyebrow">
          <span>一体化业务数据平台</span><i aria-hidden="true" />
        </p>
        <h1 id="platform-title">
          以客群为核心，<br>让业务数据相连。
        </h1>
        <p class="story-description">
          汇聚客户、招投标、政策与六级行业场景，<br class="desktop-break">以统一码表对齐数据口径，提供全天候爬虫监测与 AI 智能打标。
        </p>

        <figure
          class="hub-topology"
          role="img"
          aria-label="客群关联客户管理、招投标、政策、场景与码表管理；爬虫监测作为独立模块运行。"
        >
          <div class="hub-grid">
            <div class="hub-col">
              <div
                v-for="node in LEFT_NODES"
                :key="node.title"
                class="hub-node"
              >
                <span :class="['hub-icon', node.tone]"><component
                  :is="node.icon"
                  aria-hidden="true"
                /></span>
                <div class="hub-meta">
                  <strong>{{ node.title }}</strong><span>{{ node.desc }}</span>
                </div>
              </div>
            </div>

            <div
              class="hub-center"
              aria-hidden="true"
            >
              <svg
                class="hub-lines"
                viewBox="0 0 200 220"
                fill="none"
              >
                <path
                  v-for="(d, idx) in FLOW_PATHS"
                  :key="idx"
                  :d="d"
                  class="flow-path"
                />
              </svg>
              <div class="hub-orb">
                <span class="hub-orb__icon"><UserFilled /></span>
                <strong>客群</strong><small>统一关标</small>
              </div>
            </div>

            <div class="hub-col">
              <div
                v-for="node in RIGHT_NODES"
                :key="node.title"
                :class="['hub-node', { 'is-independent': node.badge }]"
              >
                <span :class="['hub-icon', node.tone]"><component
                  :is="node.icon"
                  aria-hidden="true"
                /></span>
                <div class="hub-meta">
                  <strong>{{ node.title }} <em v-if="node.badge">{{ node.badge }}</em></strong>
                  <span>{{ node.desc }}</span>
                </div>
              </div>
            </div>
          </div>
        </figure>
      </div>

      <footer class="story-footer">
        <div class="story-footer__left">
          <span />数据相连，围绕客群开展业务
        </div>
        <div class="story-footer__right">
          <span>细粒度 RBAC 权限</span><i>·</i><span>全操作审计留痕</span>
        </div>
      </footer>
    </section>

    <section
      class="login-panel"
      aria-labelledby="login-title"
    >
      <div class="login-panel__top">
        <span class="iam-pill"><span class="status-dot" />统一账号登录</span>
      </div>

      <div class="login-form-wrap">
        <div class="login-card">
          <span class="welcome-label"><Connection aria-hidden="true" />欢迎回来</span>
          <h2 id="login-title">
            登录你的工作空间
          </h2>
          <p class="login-description">
            使用管理员为你分配的账号继续。
          </p>

          <form
            class="login-form"
            novalidate
            :aria-busy="loading"
            @submit.prevent="onSubmit"
          >
            <div
              v-if="submitError"
              class="login-alert"
              role="alert"
            >
              {{ submitError }}
            </div>

            <div class="login-field">
              <label for="login-username">用户名</label>
              <div
                class="input-shell"
                :class="{ 'has-error': errors.username }"
              >
                <User aria-hidden="true" />
                <input
                  id="login-username"
                  ref="usernameInput"
                  v-model="form.username"
                  name="username"
                  type="text"
                  placeholder="请输入用户名"
                  autocomplete="username"
                  autocapitalize="none"
                  :spellcheck="false"
                  :disabled="loading"
                  :aria-invalid="Boolean(errors.username)"
                  :aria-describedby="errors.username ? 'username-error' : undefined"
                  required
                  @input="clearError('username')"
                >
              </div>
              <p
                v-if="errors.username"
                id="username-error"
                class="field-error"
                role="alert"
              >
                {{ errors.username }}
              </p>
            </div>

            <div class="login-field">
              <label for="login-password">密码</label>
              <div
                class="input-shell"
                :class="{ 'has-error': errors.password }"
              >
                <Lock aria-hidden="true" />
                <input
                  id="login-password"
                  ref="passwordInput"
                  v-model="form.password"
                  name="password"
                  :type="showPassword ? 'text' : 'password'"
                  placeholder="请输入密码"
                  autocomplete="current-password"
                  :disabled="loading"
                  :aria-invalid="Boolean(errors.password)"
                  :aria-describedby="errors.password ? 'password-error' : capsLock ? 'caps-lock-hint' : undefined"
                  required
                  @input="clearError('password')"
                  @keydown="checkCapsLock"
                  @keyup="checkCapsLock"
                  @blur="capsLock = false"
                >
                <button
                  class="password-toggle"
                  type="button"
                  :disabled="loading"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  :aria-pressed="showPassword"
                  @click="showPassword = !showPassword"
                >
                  <Hide
                    v-if="showPassword"
                    aria-hidden="true"
                  /><View
                    v-else
                    aria-hidden="true"
                  />
                </button>
              </div>
              <p
                v-if="errors.password"
                id="password-error"
                class="field-error"
                role="alert"
              >
                {{ errors.password }}
              </p>
              <p
                v-if="capsLock"
                id="caps-lock-hint"
                class="caps-lock"
                role="status"
              >
                大写锁定已开启，请留意密码大小写。
              </p>
            </div>

            <button
              class="login-submit"
              type="submit"
              :disabled="loading"
            >
              <span
                v-if="loading"
                class="login-spinner"
                aria-hidden="true"
              />
              <span>{{ loading ? '正在登录…' : '登录' }}</span>
              <ArrowRight
                v-if="!loading"
                aria-hidden="true"
              />
            </button>
            <p class="login-help">
              忘记密码或需要开通账号？请联系系统管理员。
            </p>
          </form>

          <div class="login-note">
            <Lock aria-hidden="true" /><span>登录后，按账号权限访问相应模块</span>
          </div>
        </div>
      </div>

      <footer class="login-panel__footer">
        业务数据运营平台<span>统一入口 · 高效协同</span>
      </footer>
    </section>
  </main>
</template>

<style scoped>
.login { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(460px, 0.95fr); min-height: 100vh; min-height: 100dvh; background: #f8fafc; }
.login-story { position: relative; isolation: isolate; display: flex; flex-direction: column; justify-content: space-between; overflow: hidden; padding: 38px clamp(32px, 4.2vw, 72px) 28px; color: #fff; background: radial-gradient(circle at 88% 12%, rgba(59, 130, 246, 0.34) 0%, transparent 48%), radial-gradient(circle at 12% 88%, rgba(14, 165, 233, 0.2) 0%, transparent 45%), linear-gradient(145deg, #0b192c 0%, #102a4c 54%, #173b6c 100%); }
.login-story::before { content: ""; position: absolute; inset: 0; pointer-events: none; opacity: 0.14; background-image: linear-gradient(to right, rgba(255, 255, 255, 0.14) 1px, transparent 1px), linear-gradient(to bottom, rgba(255, 255, 255, 0.14) 1px, transparent 1px); background-size: 40px 40px; }
.login-brand-bar { position: relative; z-index: 1; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.login-brand { display: flex; align-items: center; gap: 12px; }
.brand-mark { display: flex; align-items: center; justify-content: center; gap: 3.5px; width: 38px; height: 38px; border-radius: 10px; background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.18); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2); }
.brand-mark i { width: 4px; height: 16px; border-radius: 2px; background: #bae6fd; transform: skewY(-22deg); } .brand-mark i:nth-child(2) { height: 22px; background: #fff; } .brand-mark i:nth-child(3) { background: #60a5fa; }
.brand-text { display: flex; flex-direction: column; gap: 2px; } .brand-title { font-size: 16px; font-weight: 650; letter-spacing: 0.6px; color: #fff; line-height: 1.2; } .brand-sub { font-size: 10px; font-weight: 600; letter-spacing: 1.4px; color: rgba(186, 230, 253, 0.72); }
.story-badge { display: inline-flex; align-items: center; gap: 7px; padding: 5px 12px; border-radius: 999px; background: rgba(56, 189, 248, 0.13); border: 1px solid rgba(125, 211, 252, 0.26); color: #e0f2fe; font-size: 12px; font-weight: 500; }
.story-badge i { width: 6px; height: 6px; border-radius: 50%; background: #34d399; box-shadow: 0 0 8px #34d399; }
.story-content { position: relative; z-index: 1; width: 100%; max-width: 680px; margin: auto; padding: 28px 0; }
.eyebrow { display: inline-flex; align-items: center; gap: 10px; margin: 0 0 14px; color: #7dd3fc; font-size: 12px; font-weight: 600; letter-spacing: 3px; } .eyebrow i { width: 28px; height: 1px; background: rgba(125, 211, 252, 0.45); }
h1 { margin: 0; font-size: clamp(32px, 3vw, 46px); font-weight: 700; line-height: 1.25; letter-spacing: 1px; } .story-description { margin: 16px 0 0; color: rgba(226, 232, 240, 0.86); font-size: 14px; line-height: 1.85; }
.hub-topology { margin: 28px 0 0; padding: 20px; border-radius: 18px; background: rgba(15, 23, 42, 0.42); border: 1px solid rgba(255, 255, 255, 0.14); backdrop-filter: blur(12px); box-shadow: 0 20px 44px rgba(2, 6, 23, 0.32); }
.hub-grid { display: grid; grid-template-columns: 1fr 148px 1fr; align-items: center; gap: 10px; } .hub-col { display: flex; flex-direction: column; gap: 10px; position: relative; z-index: 2; }
.hub-node { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 12px; background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.14); transition: background 0.16s, border-color 0.16s; }
.hub-node:hover { background: rgba(255, 255, 255, 0.13); border-color: rgba(125, 211, 252, 0.35); } .hub-node.is-independent { background: rgba(2, 6, 23, 0.45); border: 1px dashed rgba(125, 211, 252, 0.36); }
.hub-icon { display: grid; place-items: center; flex: 0 0 32px; width: 32px; height: 32px; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.18); } .hub-icon svg { width: 16px; height: 16px; }
.hub-icon.is-blue { background: rgba(59, 130, 246, 0.25); color: #bfdbfe; } .hub-icon.is-indigo { background: rgba(99, 102, 241, 0.25); color: #c7d2fe; } .hub-icon.is-sky { background: rgba(14, 165, 233, 0.25); color: #bae6fd; }
.hub-icon.is-emerald { background: rgba(16, 185, 129, 0.25); color: #a7f3d0; } .hub-icon.is-amber { background: rgba(245, 158, 11, 0.25); color: #fde68a; } .hub-icon.is-purple { background: rgba(168, 85, 247, 0.25); color: #e9d5ff; }
.hub-meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; } .hub-meta strong { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; color: #fff; white-space: nowrap; }
.hub-meta strong em { font-style: normal; font-size: 10px; font-weight: 500; padding: 1px 5px; border-radius: 4px; background: rgba(56, 189, 248, 0.18); color: #bae6fd; }
.hub-meta span { font-size: 11px; color: rgba(203, 213, 225, 0.78); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hub-center { position: relative; display: flex; align-items: center; justify-content: center; height: 100%; min-height: 196px; } .hub-lines { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.flow-path { stroke: rgba(125, 211, 252, 0.52); stroke-width: 1.6; stroke-dasharray: 5 5; animation: hub-flow 3.2s linear infinite; } @keyframes hub-flow { to { stroke-dashoffset: -40; } }
.hub-orb { position: relative; z-index: 2; display: flex; flex-direction: column; align-items: center; justify-content: center; width: 98px; height: 98px; border-radius: 50%; text-align: center; background: radial-gradient(circle at 35% 30%, rgba(59, 130, 246, 0.52), rgba(14, 116, 144, 0.36)); border: 2px solid rgba(125, 211, 252, 0.68); box-shadow: 0 0 28px rgba(56, 189, 248, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.35); }
.hub-orb__icon { display: grid; place-items: center; width: 26px; height: 26px; margin-bottom: 3px; border-radius: 50%; background: rgba(255, 255, 255, 0.16); color: #e0f2fe; } .hub-orb__icon svg { width: 14px; height: 14px; }
.hub-orb strong { font-size: 14px; font-weight: 700; color: #fff; letter-spacing: 1px; } .hub-orb small { font-size: 11px; color: #bae6fd; margin-top: 1px; }
.story-footer { position: relative; z-index: 1; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 16px; border-top: 1px solid rgba(255, 255, 255, 0.1); color: rgba(186, 230, 253, 0.76); font-size: 12px; }
.story-footer__left, .story-footer__right { display: flex; align-items: center; gap: 8px; } .story-footer__left > span { width: 22px; height: 1px; background: rgba(125, 211, 252, 0.6); } .story-footer__right i { font-style: normal; opacity: 0.5; }
.login-panel { display: flex; flex-direction: column; justify-content: space-between; padding: 36px clamp(28px, 4.5vw, 76px) 28px; background-color: #f8fafc; background-image: radial-gradient(rgba(148, 163, 184, 0.26) 1px, transparent 1px); background-size: 20px 20px; }
.login-panel__top { display: flex; align-items: center; justify-content: flex-end; } .status-dot { width: 6px; height: 6px; border-radius: 50%; background: #2563eb; }
.iam-pill { display: inline-flex; align-items: center; gap: 8px; padding: 5px 12px; border-radius: 999px; background: #fff; border: 1px solid #e2e8f0; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); color: #475569; font-size: 12px; font-weight: 500; }
.login-form-wrap { width: 100%; max-width: 432px; margin: auto; padding: 24px 0; }
.login-card { padding: 36px 34px 30px; border-radius: 18px; background: #fff; border: 1px solid #e2e8f0; box-shadow: 0 20px 45px -15px rgba(15, 23, 42, 0.07), 0 4px 12px rgba(15, 23, 42, 0.03); }
.welcome-label { display: inline-flex; align-items: center; gap: 6px; margin-bottom: 12px; padding: 4px 10px; border-radius: 6px; background: #eff6ff; color: #1d4ed8; font-size: 12px; font-weight: 600; } .welcome-label svg { width: 13px; height: 13px; }
h2 { margin: 0; color: #0f172a; font-size: clamp(23px, 2vw, 28px); line-height: 1.35; font-weight: 700; letter-spacing: 0.3px; } .login-description { margin: 8px 0 26px; color: #64748b; font-size: 13px; line-height: 1.65; }
.login-field { margin-bottom: 20px; } .login-field > label { display: block; margin-bottom: 8px; color: #334155; font-size: 13px; font-weight: 600; }
.input-shell { display: flex; align-items: center; height: 46px; padding: 0 14px; gap: 10px; border: 1px solid #cbd5e1; border-radius: 10px; background: #fff; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03); transition: border-color 0.16s, box-shadow 0.16s; }
.input-shell:hover { border-color: #94a3b8; } .input-shell > svg { flex: 0 0 17px; width: 17px; color: #94a3b8; } .input-shell:focus-within { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.14); } .input-shell:focus-within > svg { color: #2563eb; } .input-shell.has-error { border-color: #dc2626; box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.1); }
.input-shell input { width: 100%; min-width: 0; height: 100%; border: 0; outline: none; color: #0f172a; background: transparent; font: inherit; font-size: 14px; } .input-shell input::placeholder { color: #94a3b8; font-size: 13px; }
.password-toggle { display: grid; place-items: center; flex: 0 0 32px; width: 32px; height: 32px; margin-right: -6px; padding: 6px; border: none; border-radius: 6px; background: transparent; color: #64748b; cursor: pointer; }
.password-toggle:hover { color: #2563eb; background: #eff6ff; } .password-toggle:focus-visible, .login-submit:focus-visible { outline: 3px solid #93c5fd; outline-offset: 2px; }
.login-submit { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; height: 46px; margin-top: 24px; border: 1px solid #1d4ed8; border-radius: 10px; color: #fff; background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%); box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.22); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.16s ease; }
.login-submit:hover:not(:disabled) { background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%); box-shadow: 0 6px 16px rgba(37, 99, 235, 0.34), inset 0 1px 0 rgba(255, 255, 255, 0.28); transform: translateY(-1px); }
.login-submit svg { width: 16px; } .login-submit:disabled { cursor: wait; opacity: 0.75; } .password-toggle:disabled { cursor: default; opacity: 0.5; }
.login-help { margin: 16px 0 0; color: #64748b; font-size: 12px; line-height: 1.7; text-align: center; } .login-note { display: flex; align-items: center; justify-content: center; gap: 6px; margin-top: 22px; padding-top: 18px; border-top: 1px solid #f1f5f9; color: #64748b; font-size: 12px; } .login-note svg { width: 14px; color: #10b981; }
.login-panel__footer { display: flex; justify-content: space-between; gap: 16px; color: #94a3b8; font-size: 12px; }
.login-alert { margin-bottom: 18px; padding: 11px 14px; border: 1px solid #fecaca; border-radius: 8px; background: #fef2f2; color: #b91c1c; font-size: 13px; line-height: 1.55; overflow-wrap: anywhere; }
.field-error, .caps-lock { margin: 7px 0 0; font-size: 12px; line-height: 1.5; } .field-error { color: #dc2626; } .caps-lock { color: #b45309; }
.login-spinner { width: 16px; height: 16px; border: 2px solid #ffffff55; border-top-color: #fff; border-radius: 50%; animation: login-spin 0.8s linear infinite; } @keyframes login-spin { to { transform: rotate(360deg); } }
@media (max-width: 1180px) { .login { grid-template-columns: minmax(0, 1.05fr) minmax(410px, 0.95fr); } .hub-grid { grid-template-columns: 1fr 110px 1fr; } .hub-orb { width: 84px; height: 84px; } }
@media (max-width: 900px) { .login { grid-template-columns: 1fr; } .login-story { padding: 24px 24px 28px; } .story-badge, .eyebrow, .hub-topology, .story-footer, .desktop-break, .login-panel__top { display: none; } .story-content { max-width: none; padding: 20px 0 0; } h1 { font-size: 26px; line-height: 1.35; } .story-description { margin-top: 10px; font-size: 13px; } .login-panel { padding: 24px 20px; } .login-form-wrap { max-width: 432px; padding: 4px 0 24px; } .login-card { padding: 26px 22px; } .login-panel__footer { max-width: 432px; width: 100%; margin: 0 auto; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition: none !important; animation: none !important; } }
</style>
