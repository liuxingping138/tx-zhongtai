<script setup lang="ts">
import { computed, ref } from 'vue'

import type { RoleItem } from '@/api/types'
import { roleModuleSummary } from '@/permissions/levels'

/**
 * 选角色：每个角色带上职责说明和能用多少模块，让管理员按职责选，而不是按名字猜。
 * 停用的角色不能新选，但已选的仍显示出来，允许取消。
 */
const props = defineProps<{ roles: RoleItem[]; disabled?: boolean }>()
const model = defineModel<string[]>({ required: true })

const keyword = ref('')

const visible = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  const sorted = [...props.roles].sort((a, b) =>
    Number(a.status !== 'active') - Number(b.status !== 'active')
    || Number(b.is_builtin) - Number(a.is_builtin)
    || a.name.localeCompare(b.name, 'zh-CN'))
  const usable = sorted.filter(role => role.status === 'active' || model.value.includes(role.id))
  if (!text) return usable
  return usable.filter(role => role.name.toLowerCase().includes(text) || (role.description ?? '').toLowerCase().includes(text))
})

function toggle(role: RoleItem) {
  if (props.disabled) return
  if (model.value.includes(role.id)) {
    model.value = model.value.filter(id => id !== role.id)
    return
  }
  if (role.status !== 'active') return
  model.value = [...model.value, role.id]
}

function summary(role: RoleItem): string {
  return roleModuleSummary(role.grant_counts) || '还没有设置任何模块权限'
}
</script>

<template>
  <div class="role-picker">
    <el-input
      v-if="roles.length > 6"
      v-model="keyword"
      clearable
      size="small"
      placeholder="搜索角色名称或说明"
      aria-label="搜索角色"
      class="role-picker__search"
    />
    <div
      class="role-picker__list"
      role="group"
      aria-label="选择角色"
    >
      <button
        v-for="role in visible"
        :key="role.id"
        type="button"
        role="checkbox"
        class="role-option"
        :class="{ 'is-on': model.includes(role.id), 'is-inactive': role.status !== 'active' }"
        :aria-checked="model.includes(role.id)"
        :disabled="disabled"
        @click="toggle(role)"
      >
        <span
          class="role-option__box"
          aria-hidden="true"
        />
        <span class="role-option__text">
          <span class="role-option__title">
            <strong>{{ role.name }}</strong>
            <el-tag
              v-if="role.is_builtin"
              size="small"
              type="warning"
              effect="plain"
            >
              内置
            </el-tag>
            <el-tag
              v-if="role.status !== 'active'"
              size="small"
              type="info"
            >
              已停用，取消后不能再选
            </el-tag>
            <span class="role-option__meta">{{ summary(role) }}</span>
          </span>
          <span
            v-if="role.description"
            class="role-option__desc"
          >{{ role.description }}</span>
        </span>
      </button>
      <p
        v-if="!visible.length"
        class="role-picker__empty"
      >
        {{ keyword ? '没有匹配的角色' : '还没有可用的角色，请先到「角色与权限」新增。' }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.role-picker { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.role-picker__list { display: flex; flex-direction: column; gap: 6px; max-height: 280px; overflow-y: auto; padding: 2px; }
.role-picker__empty { margin: 8px 0; font-size: 13px; color: var(--zt-ink-500); }
.role-option {
  display: flex; align-items: flex-start; gap: 10px; width: 100%; padding: 8px 12px;
  border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel);
  text-align: left; font: inherit; cursor: pointer; transition: border-color 160ms ease, background-color 160ms ease;
}
.role-option:hover:not(:disabled) { border-color: var(--el-color-primary-light-7); }
.role-option:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 1px; }
.role-option.is-on { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-5); }
.role-option.is-inactive { background: var(--zt-surface-subtle); }
.role-option:disabled { cursor: not-allowed; opacity: 0.7; }
.role-option__box {
  flex: none; width: 16px; height: 16px; margin-top: 2px; border: 1px solid var(--zt-border-strong); border-radius: 4px; background: var(--zt-panel);
  display: grid; place-items: center;
}
.role-option.is-on .role-option__box { border-color: var(--zt-blue-600); background: var(--zt-blue-600); }
.role-option.is-on .role-option__box::after {
  content: ''; width: 8px; height: 4px; margin-top: -2px; border-left: 2px solid var(--zt-on-primary); border-bottom: 2px solid var(--zt-on-primary); transform: rotate(-45deg);
}
.role-option__text { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.role-option__title { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.role-option__title strong { font-size: 14px; color: var(--zt-ink-900); font-weight: 600; }
.role-option__desc { font-size: 12px; line-height: 1.5; color: var(--zt-ink-700); }
/* 模块概括靠右，一行读完「谁 · 能用多少」。 */
.role-option__meta { margin-left: auto; padding-left: 12px; font-size: 12px; color: var(--zt-ink-500); white-space: nowrap; }
</style>
