<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Delete, Document, Key, Lock, SwitchButton, Unlock } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { getUser, getUserPermissions, listAllRoles, replaceUserRoles, updateUser, type ManagedUser } from '@/api/system'
import { errorMessage } from '@/api/errors'
import type { EffectivePermission, RoleItem } from '@/api/types'
import DetailSkeleton from '@/components/DetailSkeleton.vue'
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
const canReadRoles = computed(() => auth.canRead('system.roles'))

const user = ref<ManagedUser | null>(null)
const roles = ref<RoleItem[]>([])
const permissions = ref<EffectivePermission[]>([])
const accountActive = ref(true)
const loading = ref(false)
const loadError = ref('')
const permissionError = ref('')
const infoSaveError = ref('')
const roleSaveError = ref('')

const infoSaving = ref(false)
const roleSaving = ref(false)
const pendingInfoChange = ref(false)
const pendingRoleChange = ref(false)
const grantsVisible = ref(false)

const canManage = computed(() => user.value ? canManageRow(user.value, canEditUsers.value) : false)
const canEditInfo = computed(() => canEditUsers.value && user.value?.can_manage !== false)

const directCount = computed(() =>
  permissions.value.filter(item => item.sources.some(source => source.role_id === null)).length,
)

let loadSeq = 0

async function confirmDiscard(): Promise<boolean> {
  if (!pendingInfoChange.value && !pendingRoleChange.value) return true
  return ElMessageBox.confirm('这个用户还有未保存的修改，离开后将丢弃。', '放弃修改？', {
    type: 'warning',
    confirmButtonText: '离开',
    cancelButtonText: '留下',
  }).then(() => true, () => false)
}

onBeforeRouteLeave(async () => {
  if (infoSaving.value || roleSaving.value) return false
  return confirmDiscard()
})

onBeforeRouteUpdate(async (to, from) => {
  if (to.params.id === from.params.id) return true
  if (infoSaving.value || roleSaving.value) return false
  return confirmDiscard()
})

async function load() {
  const id = userId.value
  if (!id) return
  const seq = ++loadSeq
  loading.value = true
  loadError.value = ''
  permissionError.value = ''
  infoSaveError.value = ''
  roleSaveError.value = ''
  pendingRoleChange.value = false
  try {
    const [detail, allRoles, permsResult] = await Promise.all([
      getUser(id),
      canReadRoles.value ? listAllRoles().catch(() => []) : Promise.resolve<RoleItem[]>([]),
      getUserPermissions(id).catch(err => {
        if (seq === loadSeq) permissionError.value = errorMessage(err, '无法加载实际权限')
        return { account_active: true, items: [] }
      }),
    ])
    if (seq !== loadSeq) return
    user.value = detail
    roles.value = allRoles
    permissions.value = permsResult.items
    accountActive.value = permsResult.account_active
  } catch (error) {
    if (seq === loadSeq) loadError.value = errorMessage(error, '暂时无法加载用户信息')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function onSaveInfo(formData: { display_name: string; phone: string; email: string }) {
  if (!user.value || infoSaving.value) return
  infoSaving.value = true
  infoSaveError.value = ''
  try {
    const saved = await updateUser(user.value.id, {
      ...formData,
      version: user.value.version,
    })
    user.value = { ...user.value, ...saved }
    ElMessage.success('已保存个人信息')
    if (user.value.id === auth.user?.id) void auth.loadProfile()
  } catch (error) {
    infoSaveError.value = saveFailureText(error, false)
  } finally {
    infoSaving.value = false
  }
}

async function onSaveRoles(roleIds: string[]) {
  if (!user.value || roleSaving.value || !canGrant.value) return
  roleSaving.value = true
  roleSaveError.value = ''
  try {
    const saved = await replaceUserRoles(user.value.id, { role_ids: roleIds, version: user.value.version })
    user.value = { ...user.value, ...saved }
    pendingRoleChange.value = false
    ElMessage.success('已保存角色分配，对方下次操作时即生效')
    try {
      const perms = await getUserPermissions(user.value.id)
      permissions.value = perms.items
      accountActive.value = perms.account_active
      permissionError.value = ''
    } catch (permErr) {
      permissionError.value = errorMessage(permErr, '无法加载实际权限')
    }
  } catch (error) {
    roleSaveError.value = saveFailureText(error, false)
  } finally {
    roleSaving.value = false
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
  void getUserPermissions(user.value.id)
    .then(res => {
      permissions.value = res.items
      accountActive.value = res.account_active
      permissionError.value = ''
    })
    .catch(err => {
      permissionError.value = errorMessage(err, '无法加载实际权限')
    })
}

function openAudit() {
  if (!user.value) return
  void router.push({ name: 'system-audit', state: { auditActor: user.value.display_name } })
}

watch(userId, () => {
  void load()
}, { immediate: true })
</script>

<template>
  <div class="user-detail-page">
    <div class="user-detail__nav">
      <el-button
        link
        type="primary"
        :icon="ArrowLeft"
        @click="router.push({ name: 'system-users', query: route.query })"
      >
        返回用户管理
      </el-button>
      <span class="user-detail__nav-divider">/</span>
      <span class="user-detail__nav-name">{{ user ? user.display_name : '用户详情' }}</span>
      <span
        v-if="user"
        class="user-detail__nav-sub"
      >@{{ user.username }}</span>
    </div>

    <DetailSkeleton
      v-if="loading && !user"
      :show-hero="true"
      :sections="2"
      :fields-per-section="4"
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
      <!-- 顶部宽幅 Hero Banner (Google Workspace / Cloud IAM 风格) -->
      <UserHero :user="user">
        <template #actions>
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
        </template>
      </UserHero>

      <!-- 双栏看板：左侧资料与角色，右侧权限穿透表格 -->
      <div class="user-dashboard">
        <div class="user-dashboard__sidebar">
          <section
            class="user-card"
            aria-label="基本资料"
          >
            <UserInfoForm
              :user="user"
              :can-edit="canEditInfo"
              :saving="infoSaving"
              :save-error="infoSaveError"
              @save="onSaveInfo"
              @dirty="pendingInfoChange = $event"
            />
          </section>

          <section
            class="user-card"
            aria-label="角色配置"
          >
            <UserRoleAssign
              :user="user"
              :roles="roles"
              :can-grant="canGrant"
              :direct-count="directCount"
              :saving="roleSaving"
              :save-error="roleSaveError"
              @save="onSaveRoles"
              @dirty="pendingRoleChange = $event"
              @open-grants="grantsVisible = true"
            />
          </section>
        </div>

        <div class="user-dashboard__main">
          <EffectivePermissions
            :permissions="permissions"
            :account-active="accountActive"
            :pending-role-change="pendingRoleChange"
            :error="permissionError"
          />
        </div>
      </div>
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
.user-detail-page { display: flex; flex-direction: column; gap: 16px; width: 100%; box-sizing: border-box; padding-bottom: 24px; }
.user-detail__nav { display: flex; align-items: center; gap: 8px; font-size: 13.5px; }
.user-detail__nav-divider { color: var(--zt-ink-400); }
.user-detail__nav-name { font-weight: 600; color: var(--zt-ink-900); }
.user-detail__nav-sub { color: var(--zt-ink-500); font-family: var(--zt-font-mono, monospace); font-size: 13px; }
.user-detail__placeholder { min-height: 280px; }

.user-dashboard { display: flex; align-items: flex-start; gap: 20px; width: 100%; }
.user-dashboard__sidebar { width: 380px; flex-shrink: 0; display: flex; flex-direction: column; gap: 16px; position: sticky; top: 16px; }
.user-dashboard__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 16px; }

.user-card { background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); box-shadow: var(--zt-shadow); padding: 18px 20px; }

.user-danger-action { color: var(--zt-danger-text) !important; }

@media (max-width: 1080px) {
  .user-dashboard { flex-direction: column; }
  .user-dashboard__sidebar { width: 100%; position: static; }
}
</style>
