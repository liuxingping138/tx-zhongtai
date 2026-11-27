<script setup lang="ts">
import { computed } from 'vue'

import type { ManagedUser } from '@/api/system'
import ListEmpty from '@/components/ListEmpty.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import { lockText, sinceText } from '../sessions/loginText'
import UserAvatar from './UserAvatar.vue'
import { canManageRow, openLabel } from './userRows'

defineProps<{ users: ManagedUser[]; loading: boolean; filtered: boolean; busyUserId?: string }>()
defineEmits<{
  open: [user: ManagedUser]
  toggle: [user: ManagedUser]
  remove: [user: ManagedUser]
  'reset-password': [user: ManagedUser]
  revoke: [user: ManagedUser]
  unlock: [user: ManagedUser]
  audit: [user: ManagedUser]
  reset: []
}>()

const auth = useAuthStore()
const canGrant = computed(() => auth.canFull('system.permissions'))
const canAudit = computed(() => auth.canRead('system.audit'))
const canEditUsers = computed(() => auth.canFull('system.users'))

/** 这一行能不能停用、删除、重置密码、下线、解锁：不是超级管理员的管不了超级管理员（后端给 can_manage）。 */
function manageable(row: ManagedUser): boolean {
  return canManageRow(row, canEditUsers.value)
}

function roleNames(user: ManagedUser): string {
  return (user.roles ?? []).map(role => role.name).join('、')
}
</script>

<template>
  <TableSkeleton
    v-if="loading && users.length === 0"
    :columns="6"
    :has-actions="true"
  />
  <el-table
    v-else
    class="data-table"
    :class="{ 'is-refreshing': loading }"
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
      min-width="206"
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
      min-width="88"
      show-overflow-tooltip
    />
    <el-table-column
      label="角色"
      min-width="180"
    >
      <template #default="{ row }">
        <div class="role-cell">
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
          <el-tag
            v-if="!(row.roles ?? []).length"
            size="small"
            type="warning"
            effect="plain"
          >
            待分配角色
          </el-tag>
          <!-- 权限不全来自角色时标出来，管理员一眼知道这个人有角色之外的权限。 -->
          <el-tooltip
            v-if="row.direct_grant_count"
            :content="`角色之外单独授权了 ${row.direct_grant_count} 个模块，打开详情查看`"
            placement="top"
          >
            <el-tag
              size="small"
              type="warning"
              effect="plain"
            >
              +单独授权
            </el-tag>
          </el-tooltip>
        </div>
      </template>
    </el-table-column>
    <el-table-column
      label="状态"
      width="116"
    >
      <template #default="{ row }">
        <div class="status-cell">
          <span class="status-line">
            <el-switch
              v-if="manageable(row) && row.id !== auth.user?.id"
              :model-value="row.status === 'active'"
              :loading="busyUserId === row.id"
              :disabled="Boolean(busyUserId)"
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
            <span
              v-if="manageable(row) && row.id !== auth.user?.id && !row.locked_seconds"
              class="status-text"
            >{{ row.status === 'active' ? '启用' : '停用' }}</span>
          </span>
          <!-- 密码连续输错被锁或须改密时紧凑标注，不额外撑开列表列宽。 -->
          <div
            v-if="row.locked_seconds || row.must_change_password"
            class="status-flags"
          >
            <template v-if="row.locked_seconds">
              <span
                class="status-locked"
                :title="lockText(row.locked_seconds)"
              >已锁定</span>
              <el-button
                v-if="manageable(row)"
                link
                type="primary"
                size="small"
                :loading="busyUserId === row.id"
                :disabled="Boolean(busyUserId)"
                @click="$emit('unlock', row)"
              >
                解锁
              </el-button>
            </template>
            <el-tooltip
              v-if="row.must_change_password"
              content="下次登录须先修改密码"
              placement="top"
            >
              <el-tag
                size="small"
                type="warning"
                effect="plain"
              >
                须改密
              </el-tag>
            </el-tooltip>
          </div>
        </div>
      </template>
    </el-table-column>
    <el-table-column
      label="最近登录"
      width="108"
    >
      <template #default="{ row }">
        <span
          v-if="row.last_login_at"
          class="time-cell"
          :title="`${formatTime(row.last_login_at)}${row.last_login_ip ? `，IP ${row.last_login_ip}` : ''}`"
        >{{ sinceText(row.last_login_at) }}</span>
        <span
          v-else
          class="muted time-cell"
        >从未登录</span>
      </template>
    </el-table-column>
    <el-table-column
      label="联系方式"
      min-width="168"
    >
      <template #default="{ row }">
        <div
          v-if="row.phone || row.email"
          class="contact-cell"
        >
          <span
            v-if="row.phone"
            class="contact-cell__item"
            :title="row.phone"
          >{{ row.phone }}</span>
          <span
            v-if="row.email"
            class="contact-cell__item contact-cell__email"
            :title="row.email"
          >{{ row.email }}</span>
        </div>
        <span
          v-else
          class="muted"
        >—</span>
      </template>
    </el-table-column>
    <el-table-column
      label="创建时间"
      width="148"
    >
      <template #default="{ row }">
        <span class="muted time-cell">{{ formatTime(row.created_at) }}</span>
      </template>
    </el-table-column>
    <el-table-column
      label="操作"
      width="132"
      class-name="table-action"
    >
      <template #default="{ row }">
        <div class="row-actions">
          <button
            type="button"
            class="row-action"
            :class="{ 'row-action--primary': openLabel(row, { edit: canEditUsers, grant: canGrant }) !== '查看' }"
            @click="$emit('open', row)"
          >
            {{ openLabel(row, { edit: canEditUsers, grant: canGrant }) }}
          </button>
          <el-dropdown
            v-if="manageable(row) || canAudit"
            trigger="click"
          >
            <button
              type="button"
              class="row-action"
              :disabled="busyUserId === row.id"
            >
              更多
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-if="manageable(row) && row.id !== auth.user?.id"
                  @click="$emit('remove', row)"
                >
                  删除
                </el-dropdown-item>
                <el-dropdown-item
                  v-if="manageable(row)"
                  @click="$emit('reset-password', row)"
                >
                  重置密码
                </el-dropdown-item>
                <el-dropdown-item
                  v-if="manageable(row)"
                  @click="$emit('revoke', row)"
                >
                  强制下线
                </el-dropdown-item>
                <el-dropdown-item
                  v-if="canAudit"
                  :divided="manageable(row)"
                  @click="$emit('audit', row)"
                >
                  操作记录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.muted {
  color: var(--zt-ink-500);
}

.status-cell { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.status-line { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.status-flags { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.status-flags .el-button { margin-left: 0; padding: 0; height: auto; }
.status-locked { color: var(--zt-warning-text); font-size: 12px; font-weight: 500; }
.time-cell { font-size: 13px; white-space: nowrap; }
.contact-cell { display: flex; flex-direction: column; gap: 1px; min-width: 0; line-height: 1.4; }
.contact-cell__item { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.contact-cell__item + .contact-cell__email { color: var(--zt-ink-500); font-size: 12px; }
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

.is-refreshing {
  opacity: 0.65;
  pointer-events: none;
  transition: opacity 0.2s ease;
}
</style>
