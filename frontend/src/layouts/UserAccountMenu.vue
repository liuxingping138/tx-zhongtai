<script setup lang="ts">
import { computed } from 'vue'
import { ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/api/errors'

const props = withDefaults(defineProps<{ compact?: boolean; tone?: 'nav' | 'header' }>(), {
  compact: false,
  tone: 'nav',
})

const auth = useAuthStore()
const router = useRouter()
const name = computed(() => auth.user?.display_name || auth.user?.username || '用户')
const initial = computed(() => name.value.slice(0, 1))
const roleLine = computed(() => {
  const roles = auth.user?.roles?.filter(Boolean) ?? []
  if (!roles.length) return '未分配角色'
  if (roles.length === 1) return roles[0]!
  if (roles.length === 2) return `${roles[0]} · ${roles[1]}`
  return `${roles[0]} 等 ${roles.length} 个角色`
})
const placement = computed(() => {
  if (props.tone === 'header') return 'bottom-end'
  return props.compact ? 'top' : 'top-start'
})

async function onLogout() {
  try {
    await auth.signOut()
  } catch (error) {
    ElMessage.error(errorMessage(error, '退出失败'))
  } finally {
    await router.push({ name: 'login' })
  }
}
</script>

<template>
  <el-dropdown
    class="user-account-dropdown"
    :class="{ 'is-header': tone === 'header' }"
    trigger="click"
    :placement="placement"
    popper-class="user-account-popper"
  >
    <button
      type="button"
      class="user-account"
      :class="[`is-${tone}`, { 'is-compact': compact }]"
      :aria-label="`${name}，打开账号菜单`"
      :title="compact ? `${name}（${roleLine}）` : undefined"
    >
      <span
        class="user-account__avatar"
        aria-hidden="true"
      >{{ initial }}</span>
      <span
        v-if="!compact"
        class="user-account__meta"
      >
        <strong>{{ name }}</strong>
        <small v-if="tone !== 'header'">{{ roleLine }}</small>
      </span>
      <el-icon
        v-if="!compact"
        class="user-account__caret"
      >
        <component :is="tone === 'header' ? ArrowDown : ArrowUp" />
      </el-icon>
    </button>
    <template #dropdown>
      <el-dropdown-menu>
        <div class="user-menu-header">
          <span
            class="user-menu-header__avatar"
            aria-hidden="true"
          >{{ initial }}</span>
          <div class="user-menu-header__info">
            <strong class="user-menu-header__name">{{ name }}</strong>
            <span class="user-menu-header__role">{{ roleLine }}</span>
          </div>
        </div>
        <el-dropdown-item @click="router.push({ name: 'profile' })">
          个人设置
        </el-dropdown-item>
        <el-dropdown-item @click="onLogout">
          退出登录
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.user-account {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  gap: 10px;
  padding: 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.user-account__avatar {
  display: grid;
  place-items: center;
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 650;
}
.user-account__meta { min-width: 0; flex: 1; }
.user-account__meta strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 600; }
.user-account__meta small { display: block; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; font-weight: 400; }
.user-account__caret { flex-shrink: 0; font-size: 12px; }
.user-account.is-nav { color: var(--zt-ink-900); }
.user-account.is-nav .user-account__avatar { background: var(--el-color-primary-light-9); color: var(--zt-blue-600); }
.user-account.is-nav .user-account__meta small,
.user-account.is-nav .user-account__caret { color: var(--zt-ink-500); }
.user-account.is-nav:hover { background: var(--zt-soft); }
.user-account.is-header {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 10px 0 4px;
  border-radius: 18px;
  border: 1px solid var(--zt-border);
  background: var(--zt-panel);
  color: var(--zt-ink-800);
  width: auto;
  transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
.user-account.is-header:hover {
  background: var(--zt-surface-subtle);
  border-color: var(--zt-border-strong);
  box-shadow: var(--zt-shadow);
}
.user-account.is-header .user-account__avatar {
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--el-color-primary-light-9);
  color: var(--zt-blue-600);
  font-size: 12px;
  font-weight: 650;
}
.user-account.is-header .user-account__meta {
  display: flex;
  align-items: center;
  max-width: 120px;
}
.user-account.is-header .user-account__meta strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--zt-ink-900);
}
.user-account.is-header .user-account__caret {
  color: var(--zt-ink-400);
  font-size: 11px;
}
.user-account.is-compact { justify-content: center; padding: 6px; }
.user-account.is-header.is-compact { padding: 2px; border-radius: 10px; }
.user-account:focus-visible { outline: 2px solid var(--el-color-primary-light-5); outline-offset: 2px; }
.user-account.is-header:focus-visible { outline-color: var(--zt-blue-600); }
</style>

<style>
.user-account-dropdown { display: block; width: 100%; }
.user-account-dropdown.is-header { width: auto; }
.user-account-popper .user-menu-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px 12px;
  border-bottom: 1px solid var(--zt-divider);
  margin-bottom: 4px;
}
.user-account-popper .user-menu-header__avatar {
  display: grid;
  place-items: center;
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--el-color-primary-light-9);
  color: var(--zt-blue-600);
  font-size: 14px;
  font-weight: 650;
}
.user-account-popper .user-menu-header__info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.user-account-popper .user-menu-header__name {
  font-size: 13.5px;
  font-weight: 650;
  color: var(--zt-ink-900);
  line-height: 1.2;
}
.user-account-popper .user-menu-header__role {
  font-size: 11px;
  color: var(--zt-ink-600);
  background: var(--zt-surface-subtle);
  border: 1px solid var(--zt-border);
  border-radius: 10px;
  padding: 1px 7px;
  width: fit-content;
  line-height: 1.2;
}
.user-account-popper .user-account-identity { display: flex; flex-direction: column; gap: 2px; line-height: 1.3; }
.user-account-popper .user-account-identity strong { font-size: 13px; color: var(--zt-ink-900); }
.user-account-popper .user-account-identity small { font-size: 11px; color: var(--zt-ink-500); }
</style>
