<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Document } from '@element-plus/icons-vue'

import { getUser, getUserPermissions, replaceUserRoles } from '@/api/system'
import { errorMessage, isApiError } from '@/api/errors'
import type { EffectivePermission, RoleItem, UserItem } from '@/api/types'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { LEVEL_TEXT } from '@/permissions/catalog'
import { formatTime } from '@/utils/time'
import RolePicker from './RolePicker.vue'

const props = defineProps<{ userId: string | null; roles: RoleItem[]; canGrant: boolean; canAudit: boolean }>()
const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ changed: [user: UserItem] }>()
const router = useRouter()

const user = ref<UserItem | null>(null)
const permissions = ref<EffectivePermission[]>([])
const accountActive = ref(true)
const loading = ref(false)
const loadError = ref('')
const permissionError = ref('')
const draft = ref<string[]>([])
const saving = ref(false)
/** 默认只显示当前角色，点「调整角色」才展开选择列表，免得把实际权限挤到下面。 */
const editingRoles = ref(false)

const guard = useUnsavedForm(visible, () => [...draft.value].sort(), saving)
const STATUS_TEXT: Record<string, string> = { active: '启用', disabled: '禁用' }

const rolesDirty = computed(() => {
  const saved = [...(user.value?.role_ids ?? [])].sort()
  return JSON.stringify(saved) !== JSON.stringify([...draft.value].sort())
})

/** 按分组整理，分组内保持后端的模块顺序。 */
const grouped = computed(() => {
  const out = new Map<string, EffectivePermission[]>()
  for (const item of permissions.value) {
    const key = item.group_name || '其他'
    out.set(key, [...(out.get(key) ?? []), item])
  }
  return [...out.entries()]
})

const effectiveCount = computed(() => permissions.value.filter(item => item.level !== 'NONE').length)

let sequence = 0
async function load() {
  if (!props.userId) return
  const current = ++sequence
  loading.value = true
  loadError.value = ''
  permissionError.value = ''
  try {
    const detail = await getUser(props.userId)
    if (current !== sequence) return
    user.value = detail
    draft.value = [...(detail.role_ids ?? [])]
    guard.markSaved()
  } catch (error) {
    if (current !== sequence) return
    loadError.value = errorMessage(error, '暂时无法加载用户信息')
    loading.value = false
    return
  }
  try {
    const result = await getUserPermissions(props.userId)
    if (current !== sequence) return
    permissions.value = result.items
    accountActive.value = result.account_active
  } catch (error) {
    if (current === sequence) permissionError.value = errorMessage(error, '暂时无法计算实际权限')
  } finally {
    if (current === sequence) loading.value = false
  }
}

watch(() => [visible.value, props.userId] as const, ([open]) => {
  if (open) {
    user.value = null
    permissions.value = []
    draft.value = []
    editingRoles.value = false
    void load()
  }
}, { flush: 'sync' })

async function onSaveRoles() {
  if (!user.value || saving.value || !rolesDirty.value) return
  saving.value = true
  try {
    const saved = await replaceUserRoles(user.value.id, { role_ids: draft.value, version: user.value.version })
    user.value = { ...user.value, ...saved }
    draft.value = [...(saved.role_ids ?? draft.value)]
    guard.markSaved()
    editingRoles.value = false
    ElMessage.success('角色已更新，对方下次操作时即生效')
    emit('changed', user.value)
    const result = await getUserPermissions(user.value.id)
    permissions.value = result.items
  } catch (error) {
    ElMessage.error(isApiError(error) && error.status === 409
      ? '该用户刚被其他人修改过，请关闭后重新打开再调整。'
      : errorMessage(error, '保存角色失败'))
  } finally {
    saving.value = false
  }
}

function onCancelRoles() {
  draft.value = [...(user.value?.role_ids ?? [])]
  editingRoles.value = false
}

function sourceText(item: EffectivePermission): string {
  return item.sources
    .map(source => `${source.role_name}（${LEVEL_TEXT[source.level]}${source.active ? '' : '，角色已停用'}）`)
    .join('、')
}

async function openAudit() {
  if (!user.value || !await guard.canLeave()) return
  visible.value = false
  void router.push({ name: 'system-audit', state: { auditActor: user.value.display_name } })
}
</script>

<template>
  <el-drawer
    v-model="visible"
    class="editor-overlay user-drawer"
    :before-close="guard.beforeClose"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    size="600px"
    :title="user ? `${user.display_name}（${user.username}）` : '用户详情'"
  >
    <div
      v-loading="loading && !user"
      class="user-drawer__body"
    >
      <div
        v-if="loadError"
        class="user-drawer__error"
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
      <template v-else-if="user">
        <section class="block">
          <h3>基本信息</h3>
          <el-descriptions
            :column="2"
            border
            size="small"
          >
            <el-descriptions-item label="用户名">
              {{ user.username }}
            </el-descriptions-item>
            <el-descriptions-item label="显示名">
              {{ user.display_name }}
            </el-descriptions-item>
            <el-descriptions-item label="账号状态">
              <el-tag
                size="small"
                :type="user.status === 'active' ? 'success' : 'warning'"
              >
                {{ STATUS_TEXT[user.status] ?? user.status }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="须改密">
              {{ user.must_change_password ? '是，下次登录需修改密码' : '否' }}
            </el-descriptions-item>
            <el-descriptions-item
              label="创建时间"
              :span="2"
            >
              {{ formatTime(user.created_at) }}
            </el-descriptions-item>
          </el-descriptions>
        </section>

        <section class="block">
          <div class="block__head">
            <h3>角色</h3>
            <el-button
              v-if="canGrant && !editingRoles"
              link
              type="primary"
              @click="editingRoles = true"
            >
              调整角色
            </el-button>
            <span
              v-else-if="!canGrant"
              class="block__hint"
            >只有超级管理员可以调整角色</span>
            <span
              v-else
              class="block__hint"
            >勾选后点「保存角色」生效</span>
          </div>
          <RolePicker
            v-if="canGrant && editingRoles"
            v-model="draft"
            :roles="roles"
            :disabled="saving"
          />
          <div
            v-else
            class="role-tags"
          >
            <el-tag
              v-for="role in user.roles ?? []"
              :key="role.id"
              :type="role.status === 'active' ? 'primary' : 'info'"
              effect="plain"
            >
              {{ role.name }}{{ role.status === 'active' ? '' : '（已停用）' }}
            </el-tag>
            <span
              v-if="!(user.roles ?? []).length"
              class="muted"
            >未分配角色</span>
          </div>
          <div
            v-if="canGrant && editingRoles"
            class="role-actions"
          >
            <el-alert
              v-if="!draft.length"
              type="warning"
              :closable="false"
              show-icon
              title="取消全部角色后，该用户登录将看不到任何业务模块。"
            />
            <div class="role-actions__buttons">
              <el-button
                :disabled="saving"
                @click="onCancelRoles"
              >
                取消
              </el-button>
              <el-button
                type="primary"
                :loading="saving"
                :disabled="!rolesDirty"
                @click="onSaveRoles"
              >
                保存角色
              </el-button>
            </div>
          </div>
        </section>

        <section class="block">
          <div class="block__head">
            <h3>实际权限</h3>
            <span class="block__hint">多个角色叠加后取最高一档，共 {{ effectiveCount }} 个模块可用</span>
          </div>
          <el-alert
            v-if="!accountActive"
            type="warning"
            :closable="false"
            show-icon
            title="账号未启用，以下权限暂不生效。"
            class="block__notice"
          />
          <el-alert
            v-if="rolesDirty"
            type="info"
            :closable="false"
            show-icon
            title="下面是已保存的权限，保存角色后会刷新。"
            class="block__notice"
          />
          <p
            v-if="permissionError"
            class="muted"
            role="alert"
          >
            {{ permissionError }}
          </p>
          <el-empty
            v-else-if="!permissions.length"
            :image-size="56"
            description="还没有任何模块权限。分配一个角色后，这里会列出能用的模块。"
          />
          <div
            v-for="[group, items] in grouped"
            v-else
            :key="group"
            class="perm-group"
          >
            <h4>{{ group }}</h4>
            <div
              v-for="item in items"
              :key="item.resource_code"
              class="perm-line"
              :class="{ 'is-off': item.level === 'NONE' }"
            >
              <span class="perm-line__name">{{ item.resource_name }}</span>
              <el-tag
                size="small"
                :type="item.level === 'FULL' ? 'success' : item.level === 'NONE' ? 'info' : 'primary'"
                effect="light"
              >
                {{ item.level === 'NONE' ? '不生效' : LEVEL_TEXT[item.level] }}
              </el-tag>
              <span class="perm-line__source">来自 {{ sourceText(item) }}</span>
            </div>
          </div>
        </section>
      </template>
    </div>
    <template #footer>
      <el-button
        v-if="canAudit && user"
        :icon="Document"
        link
        type="primary"
        class="user-drawer__audit"
        @click="openAudit"
      >
        查看操作记录
      </el-button>
      <el-button
        :disabled="saving"
        @click="guard.close"
      >
        关闭
      </el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.user-drawer__body { display: flex; flex-direction: column; gap: 16px; min-height: 200px; }
.user-drawer__error { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 32px; }
.user-drawer__error p { margin: 0; color: var(--zt-ink-700); }
.block { padding: 16px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: #fff; }
.block h3 { margin: 0 0 12px; font-size: 14px; font-weight: 650; color: var(--zt-ink-900); }
.block__head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.block__head h3 { margin-bottom: 12px; }
.block__hint { font-size: 12px; color: var(--zt-ink-500); }
.block__notice { margin-bottom: 12px; }
.role-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.role-actions { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.role-actions__buttons { display: flex; justify-content: flex-end; gap: 8px; }
.role-actions__buttons .el-button + .el-button { margin-left: 0; }
.muted { color: var(--zt-ink-500); font-size: 13px; }
.perm-group + .perm-group { margin-top: 12px; }
.perm-group h4 { margin: 0 0 6px; font-size: 12px; font-weight: 600; color: var(--zt-ink-500); }
.perm-line {
  display: grid; grid-template-columns: minmax(96px, 150px) auto minmax(0, 1fr); align-items: center; gap: 12px;
  padding: 8px 0; border-top: 1px solid #f0f3f8;
}
.perm-line__name { font-size: 13px; color: var(--zt-ink-900); }
.perm-line.is-off .perm-line__name { color: var(--zt-ink-500); text-decoration: line-through; }
.perm-line__source { font-size: 12px; color: var(--zt-ink-500); overflow-wrap: anywhere; }
.user-drawer__audit { margin-right: auto; }
</style>

<style>
.user-drawer .el-drawer__footer { display: flex; align-items: center; }
</style>
