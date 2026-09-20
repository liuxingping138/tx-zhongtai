<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Hide, Lock, User, View } from '@element-plus/icons-vue'

import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/api/errors'

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

async function onSubmit() {
  if (loading.value) return
  errors.username = form.username.trim() ? '' : '请输入用户名'
  errors.password = form.password ? '' : '请输入密码'
  if (errors.username || errors.password) {
    if (errors.username) usernameInput.value?.focus()
    else passwordInput.value?.focus()
    return
  }
  submitError.value = ''
  loading.value = true
  try {
    await auth.signIn(form.username.trim(), form.password)
    const target = route.query.redirect
    const redirect = typeof target === 'string' && target.startsWith('/') && !target.startsWith('//')
      ? target
      : '/'
    await router.replace(auth.mustChangePassword ? { name: 'change-password' } : redirect)
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
      <div class="login-brand">
        <span
          class="brand-mark"
          aria-hidden="true"
        ><i /><i /><i /></span>
        <span>业务数据运营平台</span>
      </div>
      <div class="story-content">
        <p class="eyebrow">
          统一工作空间
        </p>
        <h1 id="platform-title">
          让信息有序，<br>让协作高效。
        </h1>
        <p class="story-description">
          连接政策信息、标准码表与系统管理，<br class="desktop-break">在一个工作空间里，专注每一步工作。
        </p>
        <div
          class="workspace-art"
          aria-hidden="true"
        >
          <div class="orbit orbit--outer" />
          <div class="orbit orbit--inner" />
          <div class="art-line art-line--one" />
          <div class="art-line art-line--two" />
          <div class="art-core">
            <span class="core-mark"><i /><i /><i /></span>
            <span>业务数据运营平台</span>
            <small>连接 · 整理 · 协作</small>
          </div>
          <div class="art-card art-card--policy">
            <span class="art-icon">01</span>
            <div><strong>政策管理</strong><small>信源汇聚 · 政策解读</small></div>
            <span class="art-dot" />
          </div>
          <div class="art-card art-card--codebook">
            <span class="art-icon">02</span>
            <div><strong>标准码表</strong><small>统一标准 · 有序归集</small></div>
            <span class="art-dot" />
          </div>
          <div class="art-card art-card--system">
            <span class="art-icon">03</span>
            <div><strong>系统管理</strong><small>角色权限 · 操作记录</small></div>
            <span class="art-dot" />
          </div>
        </div>
      </div>
      <div class="story-footer">
        <span />信息有序流转，工作从容开展
      </div>
    </section>

    <section
      class="login-panel"
      aria-labelledby="login-title"
    >
      <div class="login-panel__top">
        <span class="status-dot" />统一账号登录
      </div>
      <div class="login-form-wrap">
        <span class="welcome-label">欢迎回来</span>
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
      <footer class="login-panel__footer">
        业务数据运营平台<span>统一入口 · 高效协同</span>
      </footer>
    </section>
  </main>
</template>

<style scoped>
.login {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(460px, 1fr);
  min-height: 100vh;
  min-height: 100dvh;
  background: #fbfcfe;
}
.login-story {
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 42px clamp(32px, 4.3vw, 80px) 30px;
  color: #fff;
  background: radial-gradient(ellipse at 92% 8%, #305a9c 0%, transparent 55%), linear-gradient(155deg, #152f56, #1a4274 70%, #244f7e);
}
.login-story::before {
  position: absolute;
  inset: 0;
  content: '';
  pointer-events: none;
  background-image: linear-gradient(#ffffff04 1px, transparent 1px), linear-gradient(90deg, #ffffff04 1px, transparent 1px);
  background-size: 52px 52px;
}
.login-brand { display: flex; align-items: center; gap: 12px; font-size: 18px; font-weight: 650; letter-spacing: 1px; }
.brand-mark, .core-mark { display: flex; align-items: center; gap: 4px; }
.brand-mark i { width: 6px; height: 25px; border-radius: 2px; background: #d6e8ff; transform: skewY(-24deg); }
.brand-mark i:nth-child(2) { height: 34px; background: #fff; }
.brand-mark i:nth-child(3) { background: #84b4fa; }
.story-content { position: relative; width: 100%; max-width: 550px; margin: auto; padding: 60px 0 32px; }
.eyebrow { margin: 0 0 20px; color: #b4c9e6; font-size: 12px; letter-spacing: 4px; }
h1 { margin: 0; font-size: clamp(36px, 3.25vw, 54px); font-weight: 600; line-height: 1.42; letter-spacing: 2px; }
.story-description { margin: 22px 0 0; color: #bccde3; font-size: 14px; line-height: 1.95; }
.workspace-art { position: relative; height: 280px; margin-top: 36px; }
.orbit { position: absolute; border: 1px solid #abcfff1b; border-radius: 50%; transform: rotate(-25deg); }
.orbit--outer { inset: 14px 0 10px; }
.orbit--inner { inset: 47px 52px 36px; }
.art-core { position: absolute; top: 76px; left: 35%; display: flex; flex-direction: column; align-items: center; gap: 10px; font-size: 13px; }
.core-mark { justify-content: center; width: 66px; height: 66px; border: 1px solid #b9d4ff55; border-radius: 18px; background: linear-gradient(140deg, #95bfff35, #588cf717); box-shadow: 0 10px 36px #091e3933; }
.core-mark i { width: 7px; height: 22px; background: #d3e5ff; border-radius: 2px; transform: skewY(-25deg); }
.core-mark i:nth-child(2) { height: 31px; background: #fff; }
.core-mark i:nth-child(3) { background: #82b4ff; }
.art-core small { color: #a5bddc; font-size: 10px; letter-spacing: 2px; }
.art-card { position: absolute; display: flex; align-items: center; gap: 10px; padding: 15px 16px; border: 1px solid #b3ccf32e; border-radius: 10px; background: linear-gradient(110deg, #345982ef, #2c5078ed); box-shadow: 0 12px 24px #0c24401f; }
.art-card strong { display: block; font-size: 12px; font-weight: 500; letter-spacing: 1px; }
.art-card small { display: block; margin-top: 5px; font-size: 10px; color: #b9cce4; }
.art-icon { display: grid; place-items: center; width: 30px; height: 34px; border-radius: 6px; background: #8eb5ed14; color: #c8dcf7; font-size: 11px; font-variant-numeric: tabular-nums; }
.art-card--policy { top: 0; left: 0; }
.art-card--codebook { top: 84px; right: -4px; }
.art-card--system { bottom: 0; left: 22px; }
.art-dot { width: 4px; height: 4px; margin-left: 8px; background: #9ddccb; border-radius: 50%; }
.art-line { position: absolute; height: 1px; background: #b5d3ff40; transform-origin: left; }
.art-line--one { top: 69px; left: 110px; width: 110px; transform: rotate(30deg); }
.art-line--two { bottom: 56px; left: 172px; width: 90px; transform: rotate(-40deg); }
.story-footer { display: flex; align-items: center; gap: 10px; color: #9fb6d3; font-size: 11px; letter-spacing: 1px; }
.story-footer > span { width: 24px; height: 1px; background: #789dc7; }
.login-panel { display: flex; flex-direction: column; padding: 46px clamp(36px, 5.6vw, 108px) 30px; }
.login-panel__top { display: flex; align-items: center; justify-content: flex-end; gap: 8px; color: #8591a3; font-size: 12px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: #688bad; }
.login-form-wrap { width: 100%; max-width: 390px; margin: auto; padding: 70px 0; }
.welcome-label { display: block; margin-bottom: 12px; color: #5277a8; font-size: 13px; font-weight: 600; letter-spacing: 2px; }
h2 { margin: 0; color: #20324c; font-size: clamp(25px, 2.2vw, 32px); line-height: 1.4; letter-spacing: .5px; font-weight: 650; }
.login-description { margin: 12px 0 35px; color: #8490a1; font-size: 13px; line-height: 1.7; }
.login-field { margin-bottom: 23px; }
.login-field > label { display: block; margin-bottom: 10px; color: #394a62; font-size: 13px; font-weight: 600; }
.input-shell { display: flex; align-items: center; height: 50px; padding: 0 14px; gap: 10px; border: 1px solid #dfe5ee; border-radius: 8px; background: #fff; transition: border-color .16s, box-shadow .16s; }
.input-shell > svg { flex: 0 0 18px; width: 18px; color: #97a5b8; }
.input-shell:focus-within { border-color: #5487d4; box-shadow: 0 0 0 3px #2d76e510; }
.input-shell.has-error { border-color: #cd6868; }
.input-shell input { width: 100%; min-width: 0; height: 100%; border: 0; outline: none; color: #263850; background: transparent; font: inherit; font-size: 14px; }
.input-shell input::placeholder { color: #a1aaba; font-size: 13px; }
.password-toggle { display: grid; place-items: center; flex: 0 0 32px; width: 32px; height: 36px; margin-right: -6px; padding: 6px; border: none; border-radius: 5px; background: transparent; color: #8795a9; cursor: pointer; }
.password-toggle:hover { color: #2d76e5; background: #f0f5fc; }
.password-toggle:focus-visible, .login-submit:focus-visible { outline: 3px solid #92b8f0; outline-offset: 3px; }
.login-submit { display: flex; align-items: center; justify-content: center; gap: 12px; width: 100%; height: 50px; margin-top: 30px; border: 1px solid #2863b5; border-radius: 8px; color: #fff; background: #2c68bb; box-shadow: 0 7px 16px #2767b61c; font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; transition: background .16s, box-shadow .16s; }
.login-submit:hover:not(:disabled) { background: #215ba8; box-shadow: 0 8px 20px #2767b631; }
.login-submit svg { width: 17px; }
.login-submit:disabled { cursor: wait; opacity: .75; }
.password-toggle:disabled { cursor: default; opacity: .5; }
.login-help { margin: 19px 0 0; color: #8792a2; font-size: 12px; line-height: 1.8; text-align: center; }
.login-note { display: flex; align-items: center; justify-content: center; gap: 7px; margin-top: 38px; padding-top: 22px; border-top: 1px solid #e9edf3; color: #95a0af; font-size: 11px; }
.login-note svg { width: 13px; }
.login-panel__footer { display: flex; justify-content: space-between; gap: 16px; color: #99a3b2; font-size: 11px; }
.login-alert { margin-bottom: 20px; padding: 12px 14px; border: 1px solid #f0d6d6; border-radius: 7px; background: #fff5f4; color: #a94444; font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.field-error, .caps-lock { margin: 8px 0 0; font-size: 12px; line-height: 1.5; }
.field-error { color: #bc4949; }
.caps-lock { color: #946923; }
.login-spinner { width: 16px; height: 16px; border: 2px solid #ffffff55; border-top-color: #fff; border-radius: 50%; animation: login-spin .8s linear infinite; }
@keyframes login-spin { to { transform: rotate(360deg); } }
@media (min-width: 1500px) { .workspace-art { margin-top: 54px; } }
@media (max-width: 1100px) {
  .login { grid-template-columns: minmax(0, 1fr) minmax(410px, 1fr); }
  .login-story { padding: 32px; }
  .art-card { gap: 7px; padding: 12px; }
  .art-card--codebook { top: 122px; }
  .art-card--system { left: 0; }
  .art-core { left: 48%; top: 35px; }
  .login-panel { padding: 38px 36px 28px; }
}
@media (min-width: 801px) and (max-height: 800px) {
  .story-content { padding-top: 36px; padding-bottom: 22px; }
  .workspace-art { height: 240px; margin-top: 24px; }
  .art-core { top: 54px; }
  .login-form-wrap { padding: 40px 0; }
}
@media (max-width: 800px) {
  .login { grid-template-columns: 1fr; }
  .login-story { padding: 24px 28px 30px; }
  .login-brand { font-size: 16px; }
  .story-content { max-width: none; padding: 30px 0 0; }
  .eyebrow, .workspace-art, .story-footer, .desktop-break { display: none; }
  h1 { font-size: 28px; line-height: 1.4; }
  .story-description { margin-top: 12px; font-size: 12px; }
  .login-panel { padding: 32px 28px 24px; }
  .login-panel__top { display: none; }
  .login-form-wrap { max-width: 430px; padding: 10px 0 38px; }
  .login-panel__footer { max-width: 430px; width: 100%; margin: 0 auto; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; }
}
</style>
