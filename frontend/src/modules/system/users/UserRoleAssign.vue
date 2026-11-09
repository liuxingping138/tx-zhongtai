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

function onCancel() {
  draft.value = [...(props.user.role_ids ?? [])]
}

function onSubmit() {
  emit('save', draft.value)
}
</script>

<template>
  <div class="user-role-assign">
    <el-alert
      v-if="saveError"
      :title="saveError"
      type="error"
      show-icon
      :closable="false"
      class="user-alert"
    />
    <div class="user-role-head">
      <h3>已绑定的角色</h3>
      <span
        v-if="!canGrant"
        class="user-muted"
      >分配角色需要超级管理员权限</span>
    </div>

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
          @click="onCancel"
        >
          取消
        </el-button>
        <el-button
          type="primary"
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
      <span>{{ directCount ? `角色之外还单独授权了 ${directCount} 个模块` : '角色之外无单独授权模块' }}</span>
      <el-button
        v-if="canGrant"
        link
        type="primary"
        @click="emit('open-grants')"
      >
        管理单独授权
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.user-role-assign { display: flex; flex-direction: column; gap: 16px; }
.user-alert { margin-bottom: 8px; }
.user-role-head { display: flex; align-items: baseline; justify-content: space-between; }
.user-role-head h3 { margin: 0; font-size: 15px; font-weight: 600; color: var(--zt-ink-900); }
.user-role-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.user-role-actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; margin-top: 12px; padding-top: 16px; border-top: 1px solid var(--zt-divider); }
.user-dirty-hint { margin-right: auto; color: var(--zt-warning-text); font-size: 13px; }
.user-direct-grants { display: flex; align-items: center; justify-content: space-between; padding-top: 16px; border-top: 1px solid var(--zt-divider); font-size: 13px; color: var(--zt-ink-700); }
.user-muted { color: var(--zt-ink-500); font-size: 12px; }
</style>
