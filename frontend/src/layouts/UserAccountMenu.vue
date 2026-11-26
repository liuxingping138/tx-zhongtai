<script setup lang="ts">
import { computed } from 'vue'
import { ArrowDown, ArrowRight, SwitchButton, User } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/api/errors'

// 仅保留顶栏外观；兼容调用方传入 tone="header"。
defineProps<{ tone?: 'header' }>()

const auth = useAuthStore()
const router = useRouter()
const name = computed(() => auth.user?.display_name || auth.user?.username || '用户')
const username = computed(() => auth.user?.username || 'admin')
const initial = computed(() => name.value.slice(0, 1))
const roleLine = computed(() => {
  const roles = auth.user?.roles?.filter(Boolean) ?? []
  if (!roles.length) return '未分配角色'
  if (roles.length === 1) return roles[0]!
  if (roles.length === 2) return `${roles[0]} · ${roles[1]}`
  return `${roles[0]} 等 ${roles.length} 个角色`
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
    trigger="click"
    placement="bottom-end"
    :show-arrow="false"
    popper-class="user-account-popper"
  >
    <button
      type="button"
      class="user-account"
      :aria-label="`${name}，打开账号菜单`"
    >
      <span
        class="user-account__avatar"
        aria-hidden="true"
      >
        {{ initial }}
        <span class="user-account__status-dot" />
      </span>
      <span class="user-account__meta">
        <strong>{{ name }}</strong>
      </span>
      <el-icon class="user-account__caret">
        <ArrowDown />
      </el-icon>
    </button>
    <template #dropdown>
      <el-dropdown-menu>
        <div class="user-menu-card">
          <div class="user-menu-card__top">
            <span
              class="user-menu-card__avatar"
              aria-hidden="true"
            >
              {{ initial }}
              <span class="user-menu-card__dot" />
            </span>
            <div class="user-menu-card__info">
              <div class="user-menu-card__title-row">
                <strong class="user-menu-card__name">{{ name }}</strong>
                <span class="user-menu-card__handle">@{{ username }}</span>
              </div>
              <div class="user-menu-card__badges">
                <span class="user-menu-card__role">{{ roleLine }}</span>
                <span class="user-menu-card__online">● 在线</span>
              </div>
            </div>
          </div>
        </div>

        <el-dropdown-item
          class="user-menu-item"
          @click="router.push({ name: 'profile' })"
        >
          <span class="user-menu-item__icon is-primary">
            <el-icon><User /></el-icon>
          </span>
          <span class="user-menu-item__body">
            <span class="user-menu-item__label">个人设置</span>
            <small class="user-menu-item__desc">账号档案、登录密码与安全会话</small>
          </span>
          <el-icon class="user-menu-item__arrow">
            <ArrowRight />
          </el-icon>
        </el-dropdown-item>

        <div class="user-menu-divider" />

        <el-dropdown-item
          class="user-menu-item is-danger"
          @click="onLogout"
        >
          <span class="user-menu-item__icon is-danger">
            <el-icon><SwitchButton /></el-icon>
          </span>
          <span class="user-menu-item__body">
            <span class="user-menu-item__label">退出登录</span>
            <small class="user-menu-item__desc">安全结束当前浏览器会话</small>
          </span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.user-account {
  display: inline-flex; align-items: center; gap: 9px; min-width: 0;
  height: 36px; padding: 0 12px 0 4px; border-radius: 999px;
  border: 1px solid var(--zt-border-strong);
  background: var(--zt-btn-sec-bg); box-shadow: var(--zt-btn-sec-shadow);
  color: var(--zt-ink-900); font: inherit; text-align: left; cursor: pointer;
  transition: all 0.18s cubic-bezier(0.2, 0, 0, 1);
}
.user-account:hover {
  background: var(--zt-btn-sec-hover-bg);
  border-color: var(--zt-blue-600);
  box-shadow: var(--zt-btn-sec-hover-shadow);
  transform: translateY(-0.5px);
}
.user-account__avatar {
  position: relative; display: grid; place-items: center;
  flex: 0 0 28px; width: 28px; height: 28px; border-radius: 50%;
  background: var(--zt-avatar-gradient); color: var(--el-color-white);
  font-size: 12.5px; font-weight: 650; box-shadow: var(--zt-avatar-ring);
}
.user-account__status-dot {
  position: absolute; right: -1px; bottom: -1px; width: 9px; height: 9px;
  border-radius: 50%; background: var(--zt-success); border: 2px solid var(--zt-panel);
}
.user-account__meta { display: flex; align-items: center; min-width: 0; max-width: 120px; flex: 1; }
.user-account__meta strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 600; color: var(--zt-ink-900); }
.user-account__caret { flex-shrink: 0; color: var(--zt-ink-500); font-size: 12px; transition: transform 0.18s ease, color 0.18s ease; }
.user-account:hover .user-account__caret { color: var(--zt-blue-600); }
.user-account:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
</style>

<style>
.user-account-dropdown { display: block; width: auto; }
.user-account-popper.el-popper {
  border-radius: 16px !important;
  border: 1px solid var(--zt-border) !important;
  background: var(--zt-panel) !important;
  box-shadow: var(--zt-popper-shadow) !important;
  overflow: hidden;
}
.user-account-popper .el-popper__arrow { display: none !important; }
.user-account-popper .el-dropdown-menu {
  width: 284px; padding: 10px !important; background: transparent !important; border: 0 !important;
}
.user-account-popper .user-menu-card {
  padding: 14px; margin-bottom: 8px; border-radius: 12px;
  background: var(--zt-hero-gradient);
  border: 1px solid var(--el-color-primary-light-7);
}
.user-account-popper .user-menu-card__top { display: flex; align-items: center; gap: 12px; }
.user-account-popper .user-menu-card__avatar {
  position: relative; display: grid; place-items: center;
  flex: 0 0 44px; width: 44px; height: 44px; border-radius: 50%;
  background: var(--zt-avatar-gradient); color: var(--el-color-white);
  font-size: 18px; font-weight: 650; box-shadow: var(--zt-avatar-ring);
}
.user-account-popper .user-menu-card__dot {
  position: absolute; right: 0; bottom: 0; width: 11px; height: 11px;
  border-radius: 50%; background: var(--zt-success); border: 2px solid var(--zt-panel);
}
.user-account-popper .user-menu-card__info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.user-account-popper .user-menu-card__title-row { display: flex; align-items: baseline; gap: 6px; }
.user-account-popper .user-menu-card__name { font-size: 15px; font-weight: 650; color: var(--zt-ink-900); line-height: 1.2; }
.user-account-popper .user-menu-card__handle { font-size: 12px; color: var(--zt-ink-500); font-family: monospace; }
.user-account-popper .user-menu-card__badges { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.user-account-popper .user-menu-card__role {
  font-size: 11px; font-weight: 600; color: var(--zt-blue-600);
  background: var(--el-color-primary-light-9); border: 1px solid var(--el-color-primary-light-7);
  border-radius: 999px; padding: 2px 8px; line-height: 1.3;
}
.user-account-popper .user-menu-card__online {
  font-size: 11px; font-weight: 600; color: var(--zt-success-text);
  background: var(--zt-success-soft); border: 1px solid var(--zt-success-border);
  border-radius: 999px; padding: 2px 8px; line-height: 1.3;
}
.user-account-popper .user-menu-divider { height: 1px; background: var(--zt-divider); margin: 6px 4px; }
.user-account-popper .el-dropdown-menu__item.user-menu-item {
  display: flex !important; align-items: center !important; gap: 11px !important;
  padding: 9px 10px !important; border-radius: 10px !important; line-height: 1.3 !important;
  color: var(--zt-ink-900) !important; transition: background-color 0.15s ease;
}
.user-account-popper .el-dropdown-menu__item.user-menu-item:hover,
.user-account-popper .el-dropdown-menu__item.user-menu-item:focus {
  background: var(--zt-soft) !important; color: var(--zt-blue-600) !important;
}
.user-account-popper .el-dropdown-menu__item.user-menu-item.is-danger:hover {
  background: var(--zt-danger-soft) !important; color: var(--zt-danger-text) !important;
}
.user-account-popper .user-menu-item__icon {
  display: grid; place-items: center; flex: 0 0 34px; width: 34px; height: 34px;
  border-radius: 9px; font-size: 16px;
}
.user-account-popper .user-menu-item__icon.is-primary {
  background: var(--zt-card-icon-bg); color: var(--zt-blue-600);
}
.user-account-popper .user-menu-item__icon.is-danger {
  background: var(--zt-danger-soft); color: var(--zt-danger-text);
}
.user-account-popper .user-menu-item__body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.user-account-popper .user-menu-item__label { font-size: 13.5px; font-weight: 600; color: inherit; }
.user-account-popper .user-menu-item__desc { font-size: 11.5px; color: var(--zt-ink-500); font-weight: 400; }
.user-account-popper .user-menu-item__arrow { color: var(--zt-ink-400); font-size: 13px; margin-right: 0 !important; }
</style>
