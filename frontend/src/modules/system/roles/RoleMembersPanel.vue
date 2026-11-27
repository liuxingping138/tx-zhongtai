<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { addRoleMembers, listRoleMembers, listUsers, removeRoleMember } from '@/api/system'
import { errorMessage } from '@/api/errors'
import type { RoleItem, RoleMember, UserItem } from '@/api/types'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { memberSearchParams } from './memberSearch'

const props = defineProps<{ role: RoleItem; canGrant: boolean }>()
const emit = defineEmits<{ changed: [count: number] }>()

const members = ref<RoleMember[]>([])
const loading = ref(false)
const loadError = ref('')
const removing = ref('')

const addVisible = ref(false)
const adding = ref(false)
const picked = ref<string[]>([])
const candidates = ref<UserItem[]>([])
const searching = ref(false)
const picker = ref<{ blur: () => void }>()

const STATUS_TEXT: Record<string, string> = { active: '启用', disabled: '停用' }
const memberIds = computed(() => new Set(members.value.map(member => member.id)))

let sequence = 0
async function load() {
  const current = ++sequence
  loading.value = true
  loadError.value = ''
  try {
    const result = await listRoleMembers(props.role.id)
    if (current !== sequence) return
    members.value = result.items
  } catch (error) {
    if (current !== sequence) return
    loadError.value = errorMessage(error, '暂时无法加载成员，请稍后重试。')
  } finally {
    if (current === sequence) loading.value = false
  }
}

watch(() => props.role.id, () => { void load() }, { immediate: true })

let searchSequence = 0
async function search(keyword: string) {
  const current = ++searchSequence
  searching.value = true
  try {
    const page = await listUsers(memberSearchParams(keyword))
    if (current !== searchSequence) return
    candidates.value = page.items
  } catch {
    if (current === searchSequence) candidates.value = []
  } finally {
    if (current === searchSequence) searching.value = false
  }
}

function openAdd() {
  picked.value = []
  addVisible.value = true
  void search('')
}

async function onAdd() {
  if (!picked.value.length || adding.value) return
  adding.value = true
  try {
    const result = await addRoleMembers(props.role.id, picked.value)
    members.value = result.items
    emit('changed', result.items.length)
    ElMessage.success(result.added ? `已添加 ${result.added} 位成员` : '所选用户已在该角色中')
    addVisible.value = false
  } catch (error) {
    ElMessage.error(errorMessage(error, '添加成员失败'))
  } finally {
    adding.value = false
  }
}

async function onRemove(member: RoleMember) {
  const confirmed = await ElMessageBox.confirm(
    `将「${member.display_name}」移出「${props.role.name}」后，将不再拥有这个角色带来的权限；其他角色不受影响。`,
    '移出成员',
    { type: 'warning', confirmButtonText: '移出', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!confirmed) return
  removing.value = member.id
  try {
    const result = await removeRoleMember(props.role.id, member.id)
    members.value = result.items
    emit('changed', result.items.length)
    ElMessage.success('已移出')
  } catch (error) {
    ElMessage.error(errorMessage(error, '移出失败'))
  } finally {
    removing.value = ''
  }
}

defineExpose({ reload: load })
</script>

<template>
  <div class="members">
    <div class="members__toolbar">
      <p>
        共 <strong>{{ members.length }}</strong> 位成员。在这里增减成员，和在用户管理里给人分配角色效果相同。
      </p>
      <el-tooltip
        :disabled="canGrant"
        content="只有超级管理员可以分配角色"
        placement="top"
      >
        <span>
          <el-button
            type="primary"
            :disabled="!canGrant || role.status !== 'active'"
            @click="openAdd"
          >
            添加成员
          </el-button>
        </span>
      </el-tooltip>
    </div>
    <el-alert
      v-if="role.status !== 'active'"
      type="warning"
      :closable="false"
      show-icon
      title="角色已停用：成员暂时不会获得它的任何权限，启用后恢复。停用期间不能添加新成员。"
      class="members__notice"
    />

    <div
      v-if="loadError"
      class="members__error"
      role="alert"
    >
      <p>{{ loadError }}</p>
      <el-button
        type="primary"
        @click="load"
      >
        重新加载
      </el-button>
    </div>
    <TableSkeleton
      v-else-if="loading && members.length === 0"
      :columns="props.canGrant ? 4 : 3"
      :has-actions="props.canGrant"
    />
    <el-table
      v-else
      :data="members"
      class="data-table members__table"
      :class="{ 'is-refreshing': loading }"
    >
      <template #empty>
        <el-empty
          :image-size="64"
          description="还没有成员。点「添加成员」把这个角色分给同事。"
        />
      </template>
      <el-table-column
        prop="display_name"
        label="显示名"
        min-width="116"
        show-overflow-tooltip
      />
      <el-table-column
        prop="username"
        label="用户名"
        min-width="220"
        show-overflow-tooltip
      />
      <el-table-column
        label="账号状态"
        width="96"
      >
        <template #default="{ row }">
          <el-tag
            size="small"
            :type="row.status === 'active' ? 'success' : 'info'"
          >
            {{ STATUS_TEXT[row.status] ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        v-if="canGrant"
        label="操作"
        width="88"
      >
        <template #default="{ row }">
          <button
            type="button"
            class="row-action row-action--danger"
            :disabled="Boolean(removing)"
            :aria-busy="removing === row.id"
            @click="onRemove(row)"
          >
            {{ removing === row.id ? '移出中…' : '移出' }}
          </button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="addVisible"
      class="editor-overlay"
      title="添加成员"
      width="480px"
      :close-on-click-modal="!adding"
      :close-on-press-escape="!adding"
      :show-close="!adding"
    >
      <p class="editor-help">
        选择要加入「{{ role.name }}」的用户，可多选；已在该角色中的用户不会出现在候选里。
      </p>
      <el-select
        ref="picker"
        v-model="picked"
        class="members__picker"
        multiple
        filterable
        remote
        :remote-method="search"
        :loading="searching"
        placeholder="输入用户名或姓名搜索，不输入则列出最近的用户"
        no-data-text="没有可添加的用户"
        aria-label="选择要添加的用户"
        @change="picker?.blur()"
      >
        <el-option
          v-for="user in candidates.filter(item => !memberIds.has(item.id))"
          :key="user.id"
          :label="`${user.display_name}（${user.username}）`"
          :value="user.id"
          :disabled="user.status !== 'active'"
        >
          <span>{{ user.display_name }}</span>
          <span class="members__option-meta">{{ user.username }}{{ user.status !== 'active' ? ' · 已停用' : '' }}</span>
        </el-option>
      </el-select>
      <template #footer>
        <el-button
          :disabled="adding"
          @click="addVisible = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="adding"
          :disabled="!picked.length"
          @click="onAdd"
        >
          添加{{ picked.length ? ` ${picked.length} 人` : '' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.members { display: flex; flex-direction: column; gap: 12px; }
.members__toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.members__toolbar p { margin: 0; font-size: 13px; color: var(--zt-ink-700); }
.members__notice { margin: 0; }
.members__table { border: 1px solid var(--zt-border); border-radius: var(--zt-radius); }
.members__error { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 32px; color: var(--zt-ink-700); }
.members__error p { margin: 0; }
.members__picker { width: 100%; }
.members__option-meta { margin-left: 8px; font-size: 12px; color: var(--zt-ink-500); }
</style>
