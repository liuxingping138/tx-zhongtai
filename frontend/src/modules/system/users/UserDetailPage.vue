<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Delete, Document, Key, Lock, SwitchButton, Unlock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import { getUser, getUserPermissions, listAllRoles, replaceUserRoles, updateUser, type ManagedUser } from '@/api/system'
import { errorMessage } from '@/api/errors'
import type { EffectivePermission, RoleItem } from '@/api/types'
import PasswordOnceDialog from '@/components/PasswordOnceDialog.vue'
import { useUserActions } from '@/composables/useUserActions'
import { useAuthStore } from '@/stores/auth'
import EffectivePermissions from './EffectivePermissions.vue'
import UserGrantsDrawer from './UserGrantsDrawer.vue'
import UserHero from './UserHero.vue'
import UserInfoForm from './UserInfoForm.vue'
import UserRoleAssign from './UserRoleAssign.vue'
import { canManageRow } from './userRows'
import { saveFailureText } from './userSave'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const userId = computed(() => String(route.params.id ?? ''))
const canGrant = computed(() => auth.canFull('system.permissions'))
const canAudit = computed(() => auth.canRead('system.audit'))
const canEditUsers = computed(() => auth.canFull('system.users'))

const user = ref<ManagedUser | null>(null)
const roles = ref<RoleItem[]>([])
const permissions = ref<EffectivePermission[]>([])
const accountActive = ref(true)
const loading = ref(false)
const loadError = ref('')
const permissionError = ref('')
const saveError = ref('')
const activeTab = ref('info')

const saving = ref(false)
const grantsVisible = ref(false)

const canManage = computed(() => user.value ? canManageRow(user.value, canEditUsers.value) : false)
const canEditInfo = computed(() => canEditUsers.value && user.value?.can_manage !== false)

const directCount = computed(() =>
  permissions.value.filter(item => item.sources.some(source => source.role_id === null)).length,
)

async function load() {
  if (!userId.value) return
  loading.value = true
  loadError.value = ''
  try {
    const [detail, allRoles, permsResult] = await Promise.all([
      getUser(userId.value),
      listAllRoles().catch(() => []),
      getUserPermissions(userId.value).catch(err => {
        permissionError.value = errorMessage(err, '无法加载实际权限')
        return { account_active: true, items: [] }
      }),
    ])
    user.value = detail
    roles.value = allRoles
    permissions.value = permsResult.items
    accountActive.value = permsResult.account_active
  } catch (error) {
    loadError.value = errorMessage(error, '暂时无法加载用户信息')
  } finally {
    loading.value = false
  }
}

async function onSaveInfo(formData: { display_name: string; phone: string; email: string }) {
  if (!user.value || saving.value) return
  saving.value = true
  saveError.value = ''
  try {
    const saved = await updateUser(user.value.id, {
      ...formData,
      version: user.value.version,
    })
    user.value = { ...user.value, ...saved }
    ElMessage.success('已保存个人信息')
  } catch (error) {
    saveError.value = saveFailureText(error, false)
  } finally {
    saving.value = false
  }
}

async function onSaveRoles(roleIds: string[]) {
  if (!user.value || saving.value || !canGrant.value) return
  saving.value = true
  saveError.value = ''
  try {
    const saved = await replaceUserRoles(user.value.id, { role_ids: roleIds, version: user.value.version })
    user.value = { ...user.value, ...saved }
    const perms = await getUserPermissions(user.value.id)
    permissions.value = perms.items
    accountActive.value = perms.account_active
    ElMessage.success('已保存角色分配，对方下次操作时即生效')
  } catch (error) {
    saveError.value = saveFailureText(error, false)
  } finally {
    saving.value = false
  }
}

const onceVisible = ref(false)
const oncePassword = ref('')
const onceUsername = ref('')
function showPassword(username: string, password: string) {
  onceUsername.value = username
  oncePassword.value = password
  onceVisible.value = true
}

const actions = useUserActions({
  reload: load,
  showPassword,
  deleted: () => void router.push('/system/users'),
})

function grantsSaved(result: { count: number; version: number }) {
  if (!user.value) return
  user.value = { ...user.value, version: result.version, direct_grant_count: result.count }
  void getUserPermissions(user.value.id).then(res => {
    permissions.value = res.items
    accountActive.value = res.account_active
  })
}

function openAudit() {
  if (!user.value) return
  void router.push({ name: 'system-audit', state: { auditActor: user.value.display_name } })
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="user-detail-page">
    <div class="user-detail__bar">
      <el-button
        link
        type="primary"
        :icon="ArrowLeft"
        @click="router.push('/system/users')"
      >
        返回用户管理
      </el-button>
      <div
        v-if="user"
        class="user-detail__top-actions"
      >
        <el-button
          v-if="canAudit"
          :icon="Document"
          @click="openAudit"
        >
          查看操作记录
        </el-button>
        <el-button
          v-if="canManage"
          :icon="Key"
          @click="actions.resetPassword(user)"
        >
          重置密码
        </el-button>
        <el-button
          v-if="canManage && user.id !== auth.user?.id"
          :icon="SwitchButton"
          :type="user.status === 'active' ? 'warning' : 'success'"
          plain
          @click="actions.toggleStatus(user)"
        >
          {{ user.status === 'active' ? '停用账号' : '启用账号' }}
        </el-button>
        <el-dropdown
          v-if="canManage"
          trigger="click"
        >
          <el-button>更多操作</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-if="user.locked_seconds"
                :icon="Unlock"
                @click="actions.unlock(user)"
              >
                解锁账号
              </el-dropdown-item>
              <el-dropdown-item
                :icon="Lock"
                @click="actions.revokeSessions(user)"
              >
                强制下线会话
              </el-dropdown-item>
              <el-dropdown-item
                v-if="user.id !== auth.user?.id"
                divided
                :icon="Delete"
                class="user-danger-action"
                @click="actions.remove(user)"
              >
                删除账号
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <div
      v-if="loading && !user"
      v-loading="true"
      class="user-detail__placeholder"
    />
    <el-alert
      v-else-if="loadError"
      :title="loadError"
      type="error"
      show-icon
      :closable="false"
    >
      <el-button
        link
        type="primary"
        @click="load"
      >
        重试
      </el-button>
    </el-alert>

    <template v-else-if="user">
      <UserHero :user="user" />

      <section
        class="user-panel"
        aria-label="详细信息"
      >
        <el-tabs
          v-model="activeTab"
          class="user-tabs"
        >
          <el-tab-pane
            label="基本资料"
            name="info"
          >
            <div class="user-pane">
              <UserInfoForm
                :user="user"
                :can-edit="canEditInfo"
                :saving="saving"
                :save-error="saveError"
                @save="onSaveInfo"
              />
            </div>
          </el-tab-pane>

          <el-tab-pane
            label="角色分配"
            name="roles"
          >
            <div class="user-pane">
              <UserRoleAssign
                :user="user"
                :roles="roles"
                :can-grant="canGrant"
                :direct-count="directCount"
                :saving="saving"
                :save-error="saveError"
                @save="onSaveRoles"
                @open-grants="grantsVisible = true"
              />
            </div>
          </el-tab-pane>

          <el-tab-pane
            label="有效权限矩阵"
            name="permissions"
          >
            <div class="user-pane">
              <EffectivePermissions
                :permissions="permissions"
                :account-active="accountActive"
                :pending-role-change="false"
                :error="permissionError"
              />
            </div>
          </el-tab-pane>
        </el-tabs>
      </section>
    </template>

    <UserGrantsDrawer
      v-model="grantsVisible"
      :user="user"
      @saved="grantsSaved"
    />
    <PasswordOnceDialog
      v-model="onceVisible"
      :username="onceUsername"
      :password="oncePassword"
      @closed="() => { onceUsername = ''; oncePassword = '' }"
    />
  </div>
</template>

<style scoped>
.user-detail-page { display: flex; flex-direction: column; gap: 14px; max-width: 1040px; margin: 0 auto; width: 100%; box-sizing: border-box; }
.user-detail__bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.user-detail__top-actions { display: flex; align-items: center; gap: 8px; }
.user-detail__top-actions :deep(.el-button + .el-button) { margin-left: 0; }
.user-detail__placeholder { min-height: 280px; }

.user-panel { background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); box-shadow: var(--zt-shadow); overflow: hidden; }
.user-tabs :deep(.el-tabs__header) { margin: 0; padding: 0 20px; border-bottom: 1px solid var(--zt-border); background: var(--zt-panel); }
.user-tabs :deep(.el-tabs__nav-wrap::after) { display: none; }
.user-tabs :deep(.el-tabs__item) { height: 48px; line-height: 48px; font-size: 14px; font-weight: 500; }
.user-pane { padding: 24px; }
.user-danger-action { color: var(--zt-danger-text) !important; }
</style>
