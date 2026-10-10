<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Document } from '@element-plus/icons-vue'

import { getUser, getUserPermissions, replaceUserRoles, updateUser } from '@/api/system'
import { errorMessage, isApiError } from '@/api/errors'
import type { EffectivePermission, RoleItem, UserItem } from '@/api/types'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { formatTime } from '@/utils/time'
import EffectivePermissions from './EffectivePermissions.vue'
import RolePicker from './RolePicker.vue'

/**
 * 用户的查看与编辑合在一个抽屉里：基本信息、联系方式、角色一次改完一次保存。
 * 角色能不能改由 canGrant 决定（只有超级管理员），看不到勾选框时会说明原因。
 */
const props = defineProps<{
  userId: string | null
  roles: RoleItem[]
  canEdit: boolean
  canGrant: boolean
  canAudit: boolean
}>()
const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ changed: [user: UserItem] }>()
const router = useRouter()

const user = ref<UserItem | null>(null)
const permissions = ref<EffectivePermission[]>([])
const accountActive = ref(true)
const loading = ref(false)
const loadError = ref('')
const permissionError = ref('')
const saveError = ref('')
const form = reactive({ display_name: '', phone: '', email: '' })
const draft = ref<string[]>([])
const saving = ref(false)

const STATUS_TEXT: Record<string, string> = { active: '启用', disabled: '禁用' }
const guard = useUnsavedForm(visible, () => ({ ...form, roles: [...draft.value].sort() }), saving)

const rolesDirty = computed(() => {
  const saved = [...(user.value?.role_ids ?? [])].sort()
  return JSON.stringify(saved) !== JSON.stringify([...draft.value].sort())
})
const infoDirty = computed(() => !!user.value && (
  form.display_name.trim() !== user.value.display_name
  || form.phone.trim() !== (user.value.phone ?? '')
  || form.email.trim() !== (user.value.email ?? '')
))
const editable = computed(() => props.canEdit || props.canGrant)

function fill(detail: UserItem) {
  user.value = detail
  form.display_name = detail.display_name
  form.phone = detail.phone ?? ''
  form.email = detail.email ?? ''
  draft.value = [...(detail.role_ids ?? [])]
}

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
    fill(detail)
    guard.markSaved()
  } catch (error) {
    if (current !== sequence) return
    loadError.value = errorMessage(error, '暂时无法加载用户信息')
    loading.value = false
    return
  }
  await loadPermissions(current)
}

async function loadPermissions(current = sequence) {
  if (!props.userId) return
  try {
    const result = await getUserPermissions(props.userId)
    if (current !== sequence) return
    permissions.value = result.items
    accountActive.value = result.account_active
    permissionError.value = ''
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
    saveError.value = ''
    void load()
  }
}, { flush: 'sync' })

/** 先存基本信息再存角色：两个接口各自带版本号，第二次用第一次返回的新版本。 */
async function onSave() {
  if (!user.value || saving.value) return
  saveError.value = ''
  if (!form.display_name.trim()) {
    saveError.value = '请填写显示名'
    return
  }
  if (!infoDirty.value && !rolesDirty.value) {
    visible.value = false
    return
  }
  saving.value = true
  try {
    let current = user.value
    if (infoDirty.value && props.canEdit) {
      const saved = await updateUser(current.id, {
        display_name: form.display_name.trim(),
        phone: form.phone.trim(),
        email: form.email.trim(),
        version: current.version,
      })
      current = { ...current, ...saved }
    }
    if (rolesDirty.value && props.canGrant) {
      const saved = await replaceUserRoles(current.id, { role_ids: draft.value, version: current.version })
      current = { ...current, ...saved }
    }
    fill(current)
    guard.markSaved()
    emit('changed', current)
    ElMessage.success('已保存，对方下次操作时即生效')
    visible.value = false
  } catch (error) {
    saveError.value = isApiError(error) && error.status === 409
      ? '该用户刚被其他人修改过，请关闭后重新打开再改。'
      : errorMessage(error, '保存失败，请检查后重试')
  } finally {
    saving.value = false
  }
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
        <el-alert
          v-if="saveError"
          :title="saveError"
          type="error"
          show-icon
          :closable="false"
        />
        <section class="block">
          <div class="block__head">
            <h3>基本信息</h3>
            <span class="block__hint">
              <el-tag
                size="small"
                :type="user.status === 'active' ? 'success' : 'warning'"
              >
                {{ STATUS_TEXT[user.status] ?? user.status }}
              </el-tag>
              创建于 {{ formatTime(user.created_at) }}{{ user.must_change_password ? '，下次登录需改密' : '' }}
            </span>
          </div>
          <el-form
            label-position="top"
            :disabled="saving || !canEdit"
            class="info-grid"
            @submit.prevent
          >
            <el-form-item label="用户名">
              <el-input
                :model-value="user.username"
                disabled
              />
            </el-form-item>
            <el-form-item
              label="显示名"
              required
            >
              <el-input
                v-model="form.display_name"
                autocomplete="off"
                maxlength="128"
              />
            </el-form-item>
            <el-form-item label="电话">
              <el-input
                v-model="form.phone"
                autocomplete="off"
                inputmode="tel"
                maxlength="32"
                placeholder="11 位手机号，选填"
              />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input
                v-model="form.email"
                autocomplete="off"
                inputmode="email"
                maxlength="254"
                placeholder="选填"
              />
            </el-form-item>
          </el-form>
        </section>

        <section class="block">
          <div class="block__head">
            <h3>角色</h3>
            <span
              v-if="!canGrant"
              class="block__hint"
            >分配角色需要超级管理员</span>
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
              class="block__notice block__notice--after"
              title="没有角色的账号登录后看不到任何业务模块。"
            />
          </template>
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
            <el-tag
              v-if="!(user.roles ?? []).length"
              type="warning"
              effect="plain"
            >
              待分配角色
            </el-tag>
          </div>
        </section>

        <EffectivePermissions
          :permissions="permissions"
          :account-active="accountActive"
          :pending-role-change="rolesDirty"
          :error="permissionError"
        />
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
      <span
        v-if="guard.dirty.value"
        class="editor-dirty"
        role="status"
      >有未保存的修改</span>
      <el-button
        :disabled="saving"
        @click="guard.close"
      >
        {{ editable ? '取消' : '关闭' }}
      </el-button>
      <el-button
        v-if="editable && user"
        type="primary"
        :loading="saving"
        @click="onSave"
      >
        保存
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
.block__notice--after { margin: 12px 0 0; }
.info-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 16px; }
.info-grid :deep(.el-form-item) { margin-bottom: 12px; }
.block__hint .el-tag { margin-right: 6px; }
.user-drawer__audit { margin-right: auto; }
</style>

<style>
.user-drawer .el-drawer__footer { display: flex; align-items: center; }
</style>
