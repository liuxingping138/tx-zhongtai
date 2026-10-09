<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Document } from '@element-plus/icons-vue'

import { getUser, getUserPermissions, replaceUserRoles, updateUser } from '@/api/system'
import { errorMessage, isApiError } from '@/api/errors'
import type { EffectivePermission, RoleItem, UserItem } from '@/api/types'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { LEVEL_TEXT } from '@/permissions/catalog'
import { formatTime } from '@/utils/time'
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
            title="下面是已保存的权限，保存后按新角色生效。"
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
