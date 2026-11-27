<script setup lang="ts">
import { computed } from 'vue'
import { CopyDocument, EditPen } from '@element-plus/icons-vue'

import type { RoleItem } from '@/api/types'
import type { RoleFormMode } from './RoleFormDialog.vue'

const props = defineProps<{
  role: RoleItem
  openedCount: number
  canManageRoles: boolean
  canGrant: boolean
}>()

const emit = defineEmits<{
  openForm: [mode: RoleFormMode]
  toggleStatus: []
}>()

const descText = computed(() =>
  props.role.description
  || (props.role.is_builtin
    ? '内置角色：拥有全部模块的全部权限，也是唯一能给人分配角色的角色。'
    : '还没有职责说明，可点右侧「编辑」补充。'),
)
</script>

<template>
  <header class="role-identity">
    <div class="role-identity__top">
      <div class="role-identity__left">
        <h2>{{ role.name }}</h2>
        <el-tag
          v-if="role.is_builtin"
          size="small"
          type="warning"
          effect="plain"
        >
          内置
        </el-tag>
        <span
          class="role-status-pill"
          :class="role.status === 'active' ? 'is-active' : 'is-off'"
        >
          <span class="role-status-pill__dot" />{{ role.status === 'active' ? '启用' : '已停用' }}
        </span>
        <span class="role-identity__meta">
          <span><strong>{{ role.member_count ?? 0 }}</strong> 人</span>
          <span>·</span>
          <span>已开通 <strong>{{ openedCount }}</strong> 模块</span>
          <span>·</span>
          <span class="role-identity__code">{{ role.code }}</span>
        </span>
      </div>

      <div
        v-if="canManageRoles && !role.is_builtin"
        class="role-identity__actions"
      >
        <el-tooltip
          content="编辑名称和说明"
          placement="top"
          :show-after="300"
        >
          <el-button
            size="small"
            :icon="EditPen"
            @click="emit('openForm', 'edit')"
          >
            编辑
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="canGrant ? '连同权限复制为新角色' : '复制会连同权限一起复制，只有超级管理员可以操作'"
          placement="top"
          :show-after="canGrant ? 300 : 0"
        >
          <span>
            <el-button
              size="small"
              :icon="CopyDocument"
              :disabled="!canGrant"
              @click="emit('openForm', 'copy')"
            >
              复制
            </el-button>
          </span>
        </el-tooltip>
        <el-tooltip
          :disabled="role.status === 'active' || canGrant"
          content="启用会把这个角色的权限还给它的全部成员，只有超级管理员可以操作"
          placement="top"
        >
          <span>
            <el-button
              size="small"
              :disabled="role.status !== 'active' && !canGrant"
              @click="emit('toggleStatus')"
            >
              {{ role.status === 'active' ? '停用' : '启用' }}
            </el-button>
          </span>
        </el-tooltip>
      </div>
    </div>

    <el-tooltip
      :content="descText"
      placement="bottom-start"
      :show-after="400"
      :disabled="descText.length < 48"
    >
      <p
        class="role-identity__desc"
        :class="{ 'is-empty': !role.description }"
      >
        {{ descText }}
      </p>
    </el-tooltip>
  </header>
</template>

<style scoped src="./role-detail.css"></style>
