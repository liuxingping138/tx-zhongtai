<script setup lang="ts">
import type { ManagedUser } from '@/api/system'
import { formatTime } from '@/utils/time'
import { sinceText } from '../sessions/loginText'
import UserAvatar from './UserAvatar.vue'

defineProps<{ user: ManagedUser }>()
</script>

<template>
  <section
    class="user-hero"
    aria-label="用户概览"
  >
    <div class="user-hero__avatar">
      <UserAvatar
        :user="user"
        size="large"
      />
    </div>
    <div class="user-hero__content">
      <div class="user-hero__title-row">
        <h1>{{ user.display_name }}</h1>
        <span class="user-hero__username">@{{ user.username }}</span>
        <el-tag
          size="small"
          :type="user.status === 'active' ? 'success' : 'warning'"
        >
          {{ user.status === 'active' ? '正常' : '已停用' }}
        </el-tag>
        <el-tag
          v-if="user.locked_seconds"
          size="small"
          type="danger"
        >
          已锁定
        </el-tag>
        <el-tag
          v-if="user.must_change_password"
          size="small"
          type="warning"
          effect="plain"
        >
          下次登录需改密
        </el-tag>
      </div>
      <div class="user-hero__meta">
        <span class="user-hero__meta-item">创建于 {{ formatTime(user.created_at) }}</span>
        <span class="user-hero__meta-sep">·</span>
        <span class="user-hero__meta-item">
          {{ user.last_login_at ? `最近登录：${sinceText(user.last_login_at)}` : '从未登录' }}
        </span>
        <span
          v-if="user.last_login_ip"
          class="user-hero__meta-item"
        >(IP {{ user.last_login_ip }})</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.user-hero { display: flex; align-items: center; gap: 20px; padding: 20px 24px; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); box-shadow: var(--zt-shadow); }
.user-hero__avatar { flex: none; display: flex; align-items: center; justify-content: center; width: 64px; height: 64px; font-size: 24px; }
.user-hero__avatar :deep(.user-avatar) { width: 64px; height: 64px; font-size: 24px; border-radius: 50%; }
.user-hero__content { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6px; }
.user-hero__title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.user-hero__title-row h1 { margin: 0; font-size: 20px; font-weight: 650; color: var(--zt-ink-900); }
.user-hero__username { color: var(--zt-ink-500); font-family: var(--zt-font-mono, monospace); font-size: 14px; }
.user-hero__meta { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--zt-ink-500); flex-wrap: wrap; }
.user-hero__meta-sep { opacity: 0.5; }
</style>
