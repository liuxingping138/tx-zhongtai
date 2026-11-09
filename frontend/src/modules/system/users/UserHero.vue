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
    <div class="user-hero__top">
      <div class="user-hero__avatar">
        <UserAvatar
          :user="user"
          size="large"
        />
      </div>
      <div class="user-hero__identity">
        <h1 class="user-hero__name">
          {{ user.display_name }}
        </h1>
        <span class="user-hero__username">@{{ user.username }}</span>
        <div class="user-hero__tags">
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
            需改密
          </el-tag>
        </div>
      </div>
    </div>

    <div class="user-hero__meta">
      <div class="user-hero__meta-row">
        <span class="user-hero__meta-label">创建时间</span>
        <span class="user-hero__meta-val">{{ formatTime(user.created_at) }}</span>
      </div>
      <div class="user-hero__meta-row">
        <span class="user-hero__meta-label">最近登录</span>
        <span class="user-hero__meta-val">
          {{ user.last_login_at ? sinceText(user.last_login_at) : '从未登录' }}
          <span
            v-if="user.last_login_ip"
            class="user-hero__meta-ip"
          >({{ user.last_login_ip }})</span>
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.user-hero {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  box-shadow: var(--zt-shadow);
}
.user-hero__top {
  display: flex;
  align-items: center;
  gap: 16px;
}
.user-hero__avatar {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 60px;
  height: 60px;
}
.user-hero__avatar :deep(.user-avatar) {
  width: 60px;
  height: 60px;
  font-size: 22px;
  border-radius: 50%;
}
.user-hero__identity {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.user-hero__name {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  color: var(--zt-ink-900);
  line-height: 1.3;
  word-break: break-all;
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
  flex-wrap: wrap;
  margin-top: 2px;
}
.user-hero__meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 14px;
  border-top: 1px solid var(--zt-divider);
  font-size: 12.5px;
}
.user-hero__meta-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.user-hero__meta-label {
  color: var(--zt-ink-500);
  flex-shrink: 0;
}
.user-hero__meta-val {
  color: var(--zt-ink-800);
  text-align: right;
  word-break: break-all;
}
.user-hero__meta-ip {
  color: var(--zt-ink-500);
  margin-left: 2px;
}
</style>
