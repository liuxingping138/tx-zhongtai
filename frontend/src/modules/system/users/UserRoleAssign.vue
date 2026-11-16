<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ManagedUser } from '@/api/system'
import type { RoleItem } from '@/api/types'
import RolePicker from './RolePicker.vue'

const props = defineProps<{
  user: ManagedUser
  roles: RoleItem[]
  canGrant: boolean
  directCount: number
  saving: boolean
  saveError: string
}>()

const emit = defineEmits<{
  save: [roleIds: string[]]
  dirty: [changed: boolean]
  'open-grants': []
}>()

const draft = ref<string[]>([])

watch(() => props.user, (u) => {
  if (u) draft.value = [...(u.role_ids ?? [])]
}, { immediate: true })

const dirty = computed(() => {
  const saved = [...(props.user.role_ids ?? [])].sort()
  return JSON.stringify(saved) !== JSON.stringify([...draft.value].sort())
})

watch(dirty, (val) => {
  emit('dirty', val)
}, { immediate: true })

const activeRoleCount = computed(() => (props.user.roles ?? []).filter(r => r.status === 'active').length)

function onCancel() {
  draft.value = [...(props.user.role_ids ?? [])]
}

function onSubmit() {
  emit('save', draft.value)
}
</script>

<template>
  <div class="user-role-assign">
    <div class="user-role-head">
      <div class="user-role-head__left">
        <h3 class="user-role-title">
          角色分配
        </h3>
        <span class="user-role-badge">{{ activeRoleCount }} 个角色已启用</span>
      </div>
      <span
        v-if="!canGrant"
        class="user-role-muted"
      >需超级管理员权限</span>
    </div>

    <el-alert
      v-if="saveError"
      :title="saveError"
      type="error"
      show-icon
      :closable="false"
      class="user-alert"
    />

    <template v-if="canGrant">
      <RolePicker
        v-model="draft"
        :roles="roles"
        :disabled="saving"
      />
      <el-alert
        v-if="!draft.length"
        type="warning"
        :closable="false"
        show-icon
        class="user-alert"
        title="未分配角色的账号登录后无法查看任何业务模块。"
      />
      <div
        v-if="dirty"
        class="user-role-actions"
      >
        <span class="user-dirty-hint">角色分配有未保存的改动</span>
        <el-button
          :disabled="saving"
          size="small"
          @click="onCancel"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          size="small"
          :loading="saving"
          @click="onSubmit"
        >
          保存角色配置
        </el-button>
      </div>
    </template>
    <div
      v-else
      class="user-role-tags"
    >
      <el-tag
        v-for="role in user.roles ?? []"
        :key="role.id"
        :type="role.status === 'active' ? 'primary' : 'info'"
        effect="plain"
      >
        {{ role.name }}{{ role.status === 'active' ? '' : '（已停用）' }}
      </el-tag>
      <el-tag
        v-if="!(user.roles ?? []).length"
        type="warning"
        effect="plain"
      >
        待分配角色
      </el-tag>
    </div>

    <div
      v-if="canGrant || directCount"
      class="user-direct-grants"
    >
      <span class="direct-text">{{ directCount ? `角色之外还单独授权了 ${directCount} 个模块` : '角色之外无单独授权模块' }}</span>
      <el-button
        v-if="canGrant"
        link
        type="primary"
        class="direct-btn"
        @click="emit('open-grants')"
      >
        管理单独授权
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.user-role-assign { display: flex; flex-direction: column; gap: 14px; }
.user-role-head { display: flex; align-items: center; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid var(--zt-divider); }
.user-role-head__left { display: flex; align-items: center; gap: 8px; }
.user-role-title { margin: 0; font-size: 15px; font-weight: 650; color: var(--zt-ink-900); }
.user-role-badge { font-size: 11.5px; color: var(--zt-ink-500); background: var(--zt-surface-subtle); padding: 1px 8px; border-radius: 10px; border: 1px solid var(--zt-border); }
.user-role-muted { color: var(--zt-ink-400); font-size: 12px; }
.user-alert { margin-bottom: 4px; }

.user-role-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.user-role-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding-top: 12px; border-top: 1px solid var(--zt-divider); }
.user-dirty-hint { margin-right: auto; color: var(--zt-warning-text); font-size: 12px; }

.user-direct-grants { display: flex; align-items: center; justify-content: space-between; padding-top: 12px; border-top: 1px solid var(--zt-divider); font-size: 12.5px; color: var(--zt-ink-700); }
.direct-text { display: flex; align-items: center; gap: 6px; }
.direct-btn { font-size: 12.5px; }
</style>
