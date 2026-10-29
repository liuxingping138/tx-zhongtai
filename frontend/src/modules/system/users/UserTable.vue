<script setup lang="ts">
import { computed } from 'vue'

import type { UserItem } from '@/api/types'
import ListEmpty from '@/components/ListEmpty.vue'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import { lockText, sinceText } from '../sessions/loginText'
import UserAvatar from './UserAvatar.vue'

defineProps<{ users: UserItem[]; loading: boolean; filtered: boolean }>()
defineEmits<{
  open: [user: UserItem]
  toggle: [user: UserItem]
  remove: [user: UserItem]
  'reset-password': [user: UserItem]
  revoke: [user: UserItem]
  unlock: [user: UserItem]
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
          <UserAvatar :user="row" />
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
      width="160"
    >
      <template #default="{ row }">
        <span class="status-line">
          <el-switch
            v-if="canEditUsers && row.id !== auth.user?.id"
            :model-value="row.status === 'active'"
            :aria-label="`${row.username} 的账号启用`"
            @change="$emit('toggle', row)"
          />
          <el-tag
            v-else
            :type="row.status === 'active' ? 'success' : 'warning'"
            size="small"
          >
            {{ row.status === 'active' ? '启用' : '停用' }}
          </el-tag>
          <!-- 密码连续输错被锁：账号仍是启用，但这几分钟登不进来，直接给「解锁」。只占一行，行高不变。 -->
          <template v-if="row.locked_seconds">
            <span
              class="status-locked"
              :title="lockText(row.locked_seconds)"
            >已锁定</span>
            <el-button
              v-if="canEditUsers"
              link
              type="primary"
              @click="$emit('unlock', row)"
            >
              解锁
            </el-button>
          </template>
          <span
            v-else-if="canEditUsers && row.id !== auth.user?.id"
            class="status-text"
          >{{ row.status === 'active' ? '启用' : '停用' }}</span>
        </span>
      </template>
    </el-table-column>
    <el-table-column
      label="最近登录"
      width="150"
    >
      <template #default="{ row }">
        <span
          v-if="row.last_login_at"
          :title="`${formatTime(row.last_login_at)}${row.last_login_ip ? `，IP ${row.last_login_ip}` : ''}`"
        >{{ sinceText(row.last_login_at) }}</span>
        <span
          v-else
          class="muted"
        >从未登录</span>
      </template>
    </el-table-column>
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
      width="190"
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

.status-line { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.status-line .el-button { margin-left: 0; }
.status-locked { color: var(--zt-warning-text); font-size: 13px; }
.user-cell { display: inline-flex; align-items: center; gap: 10px; max-width: 100%; vertical-align: middle; }
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
  white-space: nowrap;
  font-size: 12px;
  color: var(--zt-ink-500);
}
</style>
