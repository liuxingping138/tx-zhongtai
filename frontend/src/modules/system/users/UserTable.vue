<script setup lang="ts">
import { computed } from 'vue'

import type { UserItem } from '@/api/types'
import ListEmpty from '@/components/ListEmpty.vue'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import { avatarText, avatarTone } from './userAvatar'

defineProps<{ users: UserItem[]; loading: boolean; filtered: boolean }>()
defineEmits<{
  open: [user: UserItem]
  toggle: [user: UserItem]
  remove: [user: UserItem]
  'reset-password': [user: UserItem]
  revoke: [user: UserItem]
  audit: [user: UserItem]
  reset: []
}>()

const auth = useAuthStore()
const canGrant = computed(() => auth.canFull('system.permissions'))
const canAudit = computed(() => auth.canRead('system.audit'))
const canEditUsers = computed(() => auth.canFull('system.users'))

function roleNames(user: UserItem): string {
  return (user.roles ?? []).map(role => role.name).join('、')
}
</script>

<template>
  <el-table
    v-loading="loading"
    class="data-table"
    :data="users"
    stripe
  >
    <template #empty>
      <ListEmpty
        :loading="loading"
        :filtered="filtered"
        @reset="$emit('reset')"
      />
    </template>
    <el-table-column
      label="用户名"
      min-width="230"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        <span class="user-cell">
          <span
            class="user-avatar"
            :class="`is-tone-${avatarTone(row.id)}`"
            aria-hidden="true"
          >{{ avatarText(row) }}</span>
          <el-button
            link
            type="primary"
            class="user-link"
            @click="$emit('open', row)"
          >
            {{ row.username }}
          </el-button>
        </span>
      </template>
    </el-table-column>
    <el-table-column
      prop="display_name"
      label="显示名"
      min-width="140"
      show-overflow-tooltip
    />
    <el-table-column
      label="电话"
      width="130"
    >
      <template #default="{ row }">
        <span v-if="row.phone">{{ row.phone }}</span>
        <span
          v-else
          class="muted"
        >—</span>
      </template>
    </el-table-column>
    <el-table-column
      label="邮箱"
      min-width="200"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        <span v-if="row.email">{{ row.email }}</span>
        <span
          v-else
          class="muted"
        >—</span>
      </template>
    </el-table-column>
    <el-table-column
      label="角色"
      min-width="200"
    >
      <template #default="{ row }">
        <div
          v-if="(row.roles ?? []).length"
          class="role-cell"
        >
          <el-tooltip
            v-for="role in (row.roles ?? []).slice(0, 2)"
            :key="role.id"
            :content="`${role.name}${role.status === 'active' ? '' : '（停用）'}`"
            placement="top"
            :show-after="400"
          >
            <span class="role-cell__tag">
              <el-tag
                size="small"
                :type="role.status === 'active' ? 'primary' : 'info'"
                effect="plain"
              >
                {{ role.name }}{{ role.status === 'active' ? '' : '（停用）' }}
              </el-tag>
            </span>
          </el-tooltip>
          <el-tooltip
            v-if="(row.roles ?? []).length > 2"
            :content="roleNames(row)"
            placement="top"
          >
            <el-tag
              size="small"
              type="info"
              effect="plain"
            >
              +{{ (row.roles ?? []).length - 2 }}
            </el-tag>
          </el-tooltip>
        </div>
        <el-tag
          v-else
          size="small"
          type="warning"
          effect="plain"
        >
          待分配角色
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column
      label="启用"
      width="120"
    >
      <template #default="{ row }">
        <template v-if="canEditUsers && row.id !== auth.user?.id">
          <el-switch
            :model-value="row.status === 'active'"
            :aria-label="`${row.username} 的账号启用`"
            @change="$emit('toggle', row)"
          />
          <span class="status-text">{{ row.status === 'active' ? '启用' : '停用' }}</span>
        </template>
        <el-tag
          v-else
          :type="row.status === 'active' ? 'success' : 'warning'"
          size="small"
        >
          {{ row.status === 'active' ? '启用' : '停用' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column
      label="须改密"
      width="90"
    >
      <template #default="{ row }">
        <el-tag
          v-if="row.must_change_password"
          size="small"
          type="warning"
          effect="plain"
        >
          是
        </el-tag>
        <span
          v-else
          class="muted"
        >否</span>
      </template>
    </el-table-column>
    <el-table-column
      label="创建时间"
      width="170"
    >
      <template #default="{ row }">
        <span class="muted">{{ formatTime(row.created_at) }}</span>
      </template>
    </el-table-column>
    <el-table-column
      label="操作"
      width="150"
      fixed="right"
    >
      <template #default="{ row }">
        <el-button
          link
          type="primary"
          @click="$emit('open', row)"
        >
          {{ canGrant && !(row.roles ?? []).length ? '分配角色' : canEditUsers || canGrant ? '编辑' : '查看' }}
        </el-button>
        <el-dropdown
          v-if="canEditUsers || canAudit"
          class="ops-more"
          trigger="click"
        >
          <el-button
            link
            type="primary"
          >
            更多
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-if="canEditUsers && row.id !== auth.user?.id"
                @click="$emit('remove', row)"
              >
                删除
              </el-dropdown-item>
              <el-dropdown-item
                v-if="canEditUsers"
                @click="$emit('reset-password', row)"
              >
                重置密码
              </el-dropdown-item>
              <el-dropdown-item
                v-if="canEditUsers"
                @click="$emit('revoke', row)"
              >
                强制下线
              </el-dropdown-item>
              <el-dropdown-item
                v-if="canAudit"
                :divided="canEditUsers"
                @click="$emit('audit', row)"
              >
                操作记录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.muted {
  color: var(--zt-ink-500);
}

.user-cell { display: inline-flex; align-items: center; gap: 10px; max-width: 100%; vertical-align: middle; }
.user-avatar { display: inline-grid; flex: none; place-items: center; width: 28px; height: 28px; border-radius: 50%; color: var(--el-color-white); font-size: 13px; font-weight: 600; line-height: 1; }
.user-avatar.is-tone-1 { background: var(--zt-avatar-1); }
.user-avatar.is-tone-2 { background: var(--zt-avatar-2); }
.user-avatar.is-tone-3 { background: var(--zt-avatar-3); }
.user-avatar.is-tone-4 { background: var(--zt-avatar-4); }
.user-avatar.is-tone-5 { background: var(--zt-avatar-5); }
.user-avatar.is-tone-6 { background: var(--zt-avatar-6); }
.user-link { overflow: hidden; min-width: 0; font-weight: 500; }
.user-link :deep(span) { overflow: hidden; text-overflow: ellipsis; }

.ops-more {
  margin-left: 12px;
  vertical-align: middle;
}

.role-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}

.role-cell__tag {
  max-width: 100%;
}

.role-cell :deep(.el-tag) {
  height: auto;
  max-width: 100%;
  padding: 1px 8px;
  line-height: 20px;
  white-space: normal;
}

.role-cell :deep(.el-tag__content) {
  white-space: normal;
}

.status-text {
  margin-left: 6px;
  white-space: nowrap;
  font-size: 12px;
  color: var(--zt-ink-500);
}
</style>
