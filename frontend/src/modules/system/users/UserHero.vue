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
    <div class="user-hero__main">
      <div class="user-hero__avatar">
        <UserAvatar :user="user" />
      </div>
      <div class="user-hero__identity">
        <div class="user-hero__title-row">
          <h1 class="user-hero__name">
            {{ user.display_name }}
          </h1>
          <span class="user-hero__username">@{{ user.username }}</span>
          <div class="user-hero__tags">
            <span
              class="user-status-pill"
              :class="user.status === 'active' ? 'is-active' : 'is-disabled'"
            >
              <span class="user-status-dot" />
              {{ user.status === 'active' ? '正常启用' : '已停用' }}
            </span>
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
              需改密
            </el-tag>
          </div>
        </div>
        <div class="user-hero__meta-row">
          <span class="user-hero__meta-item">
            <span class="user-hero__meta-label">创建时间：</span>
            <span class="user-hero__meta-val">{{ formatTime(user.created_at) }}</span>
          </span>
          <span class="user-hero__meta-sep">·</span>
          <span class="user-hero__meta-item">
            <span class="user-hero__meta-label">最近登录：</span>
            <span class="user-hero__meta-val">
              {{ user.last_login_at ? sinceText(user.last_login_at) : '从未登录' }}
              <span
                v-if="user.last_login_ip"
                class="user-hero__meta-ip"
              >({{ user.last_login_ip }})</span>
            </span>
          </span>
        </div>
      </div>
    </div>
    <div class="user-hero__actions">
      <slot name="actions" />
    </div>
  </section>
</template>

<style scoped>
.user-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 24px;
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  box-shadow: var(--zt-shadow);
  flex-wrap: wrap;
}
.user-hero__main {
  display: flex;
  align-items: center;
  gap: 18px;
  min-width: 0;
  flex: 1;
}
.user-hero__avatar {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
}
.user-hero__avatar :deep(.user-avatar) {
  width: 56px;
  height: 56px;
  font-size: 20px;
  border-radius: 50%;
  box-shadow: var(--zt-shadow);
}
.user-hero__identity {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.user-hero__title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.user-hero__name {
  margin: 0;
  font-size: 20px;
  font-weight: 650;
  color: var(--zt-ink-900);
  line-height: 1.2;
}
.user-hero__username {
  color: var(--zt-ink-500);
  font-family: var(--zt-font-mono, monospace);
  font-size: 13px;
}
.user-hero__tags {
  display: flex;
  align-items: center;
  gap: 6px;
}
.user-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.user-status-pill.is-active {
  background: var(--zt-success-soft);
  color: var(--zt-success-text);
  border: 1px solid var(--zt-success-border);
}
.user-status-pill.is-disabled {
  background: var(--zt-surface-subtle);
  color: var(--zt-ink-500);
  border: 1px solid var(--zt-border);
}
.user-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.user-status-pill.is-active .user-status-dot {
  background: var(--zt-success);
}
.user-status-pill.is-disabled .user-status-dot {
  background: var(--zt-ink-400);
}
.user-hero__meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--zt-ink-500);
  flex-wrap: wrap;
}
.user-hero__meta-item {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.user-hero__meta-label {
  color: var(--zt-ink-500);
}
.user-hero__meta-val {
  color: var(--zt-ink-800);
}
.user-hero__meta-ip {
  color: var(--zt-ink-500);
  margin-left: 2px;
}
.user-hero__meta-sep {
  color: var(--zt-ink-300);
}
.user-hero__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.user-hero__actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
</style>
