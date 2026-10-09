<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'

import {
  NO_ROLE,
  createUser,
  deleteUser,
  listAllRoles,
  listUsers,
  resetUserPassword,
  revokeUserSessions,
  updateUser,
} from '@/api/system'
import { errorMessage } from '@/api/errors'
import type { RoleItem, UserItem } from '@/api/types'
import { formatTime } from '@/utils/time'
import RolePicker from './RolePicker.vue'
import UserDetailDrawer from './UserDetailDrawer.vue'
import { useAuthStore } from '@/stores/auth'
import FilterSelect from '@/components/FilterSelect.vue'
import ListPage from '@/components/ListPage.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useListQuery } from '@/composables/useListQuery'
import ListEmpty from '@/components/ListEmpty.vue'
import { useFieldValidation } from '@/composables/useFieldValidation'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import PasswordOnceDialog from '@/components/PasswordOnceDialog.vue'

const auth = useAuthStore()
const router = useRouter()
/** 分配角色即授权，与后端同一门槛：需要「权限分配」可管理（只有超级管理员）。 */
const canGrant = computed(() => auth.canFull('system.permissions'))
const canReadRoles = computed(() => auth.canRead('system.roles'))
const canAudit = computed(() => auth.canRead('system.audit'))
const canEditUsers = computed(() => auth.canFull('system.users'))
/** 还没分配角色的账号数，给能分配角色的人一个入口直接筛出来。 */
const pendingCount = ref(0)
const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const users = ref<UserItem[]>([])
const total = ref(0)
const query = reactive({
  username: [] as string[],
  role_id: [] as string[],
  status: [] as string[],
  page: 1,
  page_size: 20,
})
const usernameOptions = ref<string[]>([])

const createVisible = ref(false)
const createForm = reactive({ username: '', display_name: '', phone: '', email: '', password: '' })
const createRoles = ref<string[]>([])
const creating = ref(false)
const allRoles = ref<RoleItem[]>([])

const detailVisible = ref(false)
const detailUserId = ref<string | null>(null)

const onceVisible = ref(false)
const oncePassword = ref('')
const onceUsername = ref('')

const createFormRef = ref<FormInstance>()
const createValidation = useFieldValidation(createForm, createFormRef)

const createGuard = useUnsavedForm(createVisible, () => ({ ...createForm, roles: createRoles.value }), creating)

function resetCreateForm() {
  createForm.username = ''
  createForm.display_name = ''
  createForm.phone = ''
  createForm.email = ''
  createForm.password = ''
}

function openCreate() {
  resetCreateForm()
  createRoles.value = []
  createVisible.value = true
  if (canGrant.value) void loadRoles()
}

async function loadRoles() {
  if (!canReadRoles.value) return
  try {
    allRoles.value = await listAllRoles()
  } catch {
    /* 角色列表失败不影响用户列表；筛选退化为不可选，分配角色处会显示空列表。 */
  }
}

const listQuery = useListQuery(query, load, ['username'])

let loadSequence = 0

async function load() {
  const params = listQuery.requested()
  void listQuery.commitPage()
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  const filtered = Object.entries(params).some(([key, value]) =>
    !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
  void loadPendingCount()
  try {
    const page = await listUsers({
      page: params.page,
      page_size: params.page_size,
      username: params.username || undefined,
      role_id: params.role_id || undefined,
      status: params.status || undefined,
    })
    if (sequence !== loadSequence) return
    users.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = errorMessage(error, '加载用户失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function loadPendingCount() {
  if (!canGrant.value) return
  try {
    pendingCount.value = (await listUsers({ page: 1, page_size: 1, role_id: NO_ROLE })).total
  } catch {
    /* 只是提示入口，失败不影响列表 */
  }
}

function showPending() {
  query.role_id = [NO_ROLE]
  onSearch()
}

function onResetFilters() {
  query.username = []
  query.role_id = []
  query.status = []
  onSearch()
}

function onSearch() {
  query.page = 1
  listQuery.captureApplied()
  void load()
}

const createError = ref('')
watch(createVisible, (open) => { if (open) { createError.value = ''; void createValidation.validate({}) } })

async function confirmCreateWithoutRole(): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      '没有角色的用户登录后看不到任何业务模块。可以先创建，之后在「待分配角色」里补。',
      '还没有选择角色',
      { type: 'warning', confirmButtonText: '仍然创建', cancelButtonText: '返回选择', distinguishCancelAndClose: true },
    )
    return true
  } catch {
    return false
  }
}

async function onCreate() {
  if (creating.value) return
  createError.value = ''
  if (!await createValidation.validate({username: createForm.username.trim() ? '' : '请填写用户名', display_name: createForm.display_name.trim() ? '' : '请填写显示名'})) return
  // 不预先挂警告，只在真要创建一个「登录后什么都看不到」的账号时确认一次。
  if (canGrant.value && !createRoles.value.length && !await confirmCreateWithoutRole()) return
  creating.value = true
  try {
    const result = await createUser({
      username: createForm.username,
      display_name: createForm.display_name,
      phone: createForm.phone.trim() || undefined,
      email: createForm.email.trim() || undefined,
      password: createForm.password || undefined,
      role_ids: canGrant.value && createRoles.value.length ? createRoles.value : undefined,
    })
    createVisible.value = false
    resetCreateForm()
    ElMessage.success(createRoles.value.length ? '用户已创建' : '用户已创建，已放进「待分配角色」')
    createRoles.value = []
    if (result.temporary_password) {
      oncePassword.value = result.temporary_password
      onceUsername.value = result.user.username
      onceVisible.value = true
    }
    await load()
  } catch (error) {
    createError.value = errorMessage(error, '创建失败，请检查后重试')
  } finally {
    creating.value = false
  }
}

async function toggleStatus(user: UserItem) {
  const next = user.status === 'active' ? 'disabled' : 'active'
  const label = next === 'disabled' ? '禁用' : '启用'
  const confirmed = await ElMessageBox.confirm(`确认${label}用户 ${user.username} ？`, '请确认', { type: 'warning' }).then(() => true, () => false)
  if (!confirmed) return
  try {
    await updateUser(user.id, { status: next, version: user.version })
    ElMessage.success(`已${label}`)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, `${label}失败`))
  }
}

async function onDelete(user: UserItem) {
  const confirmed = await ElMessageBox.confirm(
    `删除后，${user.username} 不能再登录，也不会出现在用户列表里。操作日志仍保留。这个用户名以后可以重新使用。`,
    '删除用户',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
  ).then(() => true, () => false)
  if (!confirmed) return
  try {
    await deleteUser(user.id)
    ElMessage.success('已删除')
    if (detailUserId.value === user.id) detailVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败'))
  }
}

async function onReset(user: UserItem) {
  const confirmed = await ElMessageBox.confirm(`将重置 ${user.username} 的密码并强制其下次登录改密，是否继续？`, '重置密码', {
    type: 'warning',
  }).then(() => true, () => false)
  if (!confirmed) return
  try {
    const result = await resetUserPassword(user.id)
    oncePassword.value = result.temporary_password
    onceUsername.value = user.username
    onceVisible.value = true
    ElMessage.success('已重置密码')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '重置失败'))
  }
}

async function onRevoke(user: UserItem) {
  const confirmed = await ElMessageBox.confirm(`确认强制下线 ${user.username} 的全部会话？`, '强制下线', { type: 'warning' }).then(() => true, () => false)
  if (!confirmed) return
  try {
    const result = await revokeUserSessions(user.id)
    ElMessage.success(`已撤销 ${result.revoked} 个会话`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '下线失败'))
  }
}

function roleNames(user: UserItem): string {
  return (user.roles ?? []).map(role => role.name).join('、')
}

function openDetail(user: UserItem) {
  detailUserId.value = user.id
  detailVisible.value = true
}

function onDetailChanged(user: UserItem) {
  const index = users.value.findIndex(item => item.id === user.id)
  if (index >= 0) users.value[index] = { ...users.value[index], ...user }
  void loadRoles()
  void loadPendingCount()
  if (user.id === auth.user?.id) void auth.loadProfile()
}

function openAudit(user: UserItem) {
  void router.push({ name: 'system-audit', state: { auditActor: user.display_name } })
}

function clearOnce() {
  oncePassword.value = ''
  onceUsername.value = ''
}

async function loadUsernameOptions() {
  try {
    const page = await listUsers({ page: 1, page_size: 100 })
    usernameOptions.value = page.items.map((item) => item.username)
  } catch {
    /* 选项失败不影响列表 */
  }
}

onMounted(() => {
  void load()
  void loadUsernameOptions()
  void loadRoles()
})
</script>

<template>
  <div>
    <ListPage
      title="用户管理"
      hint="账号能用哪些模块由角色决定。点「编辑」可以改信息、调角色，并看到这个人的实际权限。"
      :total="total"
      :page="query.page"
      :page-size="query.page_size"
      :loading="loading"
      :error="loadError"
      @retry="load"
      @update:page="query.page = $event"
      @update:page-size="query.page_size = $event"
      @change="load"
    >
      <template
        v-if="canGrant && pendingCount > 0"
        #summary
      >
        <div
          class="pending-bar"
          role="status"
        >
          <span>有 <strong>{{ pendingCount }}</strong> 个账号还没分配角色，登录后看不到任何模块。</span>
          <el-button
            link
            type="primary"
            @click="showPending"
          >
            只看这些
          </el-button>
        </div>
      </template>
      <template
        v-if="canEditUsers"
        #actions
      >
        <el-button
          type="primary"
          @click="openCreate"
        >
          新增用户
        </el-button>
      </template>
      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          @search="onSearch"
          @reset="onResetFilters"
        >
          <el-form-item label="用户名">
            <FilterSelect
              v-model="query.username"
              :options="usernameOptions"
              placeholder="输入或选择用户名"
            />
          </el-form-item>
          <el-form-item
            v-if="canReadRoles"
            label="角色"
          >
            <el-select
              v-model="query.role_id"
              multiple
              collapse-tags
              collapse-tags-tooltip
              clearable
              filterable
              placeholder="全部"
            >
              <el-option
                label="待分配角色"
                :value="NO_ROLE"
              />
              <el-option
                v-for="role in allRoles"
                :key="role.id"
                :label="role.name"
                :value="role.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select
              v-model="query.status"
              multiple
              collapse-tags
              collapse-tags-tooltip
              clearable
              placeholder="全部"
            >
              <el-option
                label="启用"
                value="active"
              />
              <el-option
                label="禁用"
                value="disabled"
              />
            </el-select>
          </el-form-item>
        </FilterBar>
      </template>
      <el-table
        v-loading="loading"
        class="data-table"
        :data="users"
        stripe
      >
        <template #empty>
          <ListEmpty
            :loading="loading"
            :filtered="resultFiltered"
            @reset="onResetFilters"
          />
        </template>
        <el-table-column
          label="用户名"
          width="180"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              class="user-link"
              @click="openDetail(row)"
            >
              {{ row.username }}
            </el-button>
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
          min-width="280"
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
          width="100"
        >
          <template #default="{ row }">
            <template v-if="canEditUsers && row.id !== auth.user?.id">
              <el-switch
                :model-value="row.status === 'active'"
                :aria-label="`${row.username} 的账号启用`"
                @change="toggleStatus(row)"
              />
              <span class="status-text">{{ row.status === 'active' ? '启用' : '禁用' }}</span>
            </template>
            <el-tag
              v-else
              :type="row.status === 'active' ? 'success' : 'warning'"
              size="small"
            >
              {{ row.status === 'active' ? '启用' : '禁用' }}
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
              @click="openDetail(row)"
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
                    v-if="auth.canFull('system.users') && row.id !== auth.user?.id"
                    @click="onDelete(row)"
                  >
                    删除
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-if="auth.canFull('system.users')"
                    @click="onReset(row)"
                  >
                    重置密码
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-if="auth.canFull('system.users')"
                    @click="onRevoke(row)"
                  >
                    强制下线
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-if="canAudit"
                    :divided="auth.canFull('system.users')"
                    @click="openAudit(row)"
                  >
                    操作记录
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </ListPage>

    <el-dialog
      v-model="createVisible"
      class="editor-overlay"
      :before-close="createGuard.beforeClose"
      :close-on-click-modal="!creating"
      :close-on-press-escape="!creating"
      :show-close="!creating"
      title="新增用户"
      width="560px"
    >
      <!-- autocomplete 必须写：否则浏览器把已保存的管理员账号密码填进显示名和初始密码，
           新用户会悄悄拿到管理员的密码。 -->
      <el-form
        ref="createFormRef"
        novalidate
        :disabled="creating"
        label-position="top"
      >
        <el-alert
          v-if="createError"
          :title="createError"
          type="error"
          show-icon
          :closable="false"
          class="form-submit-error"
        />
        <div class="create-grid">
          <el-form-item
            :error="createValidation.errors.username"
            label="用户名"
            required
          >
            <el-input
              v-model="createForm.username"
              autocomplete="off"
              placeholder="登录用，创建后不能改"
              :aria-invalid="Boolean(createValidation.errors.username)"
              aria-describedby="createForm-username-error"
            />
            <template #error>
              <p
                v-if="createValidation.errors.username"
                id="createForm-username-error"
                class="field-error"
                role="alert"
              >
                {{ createValidation.errors.username }}
              </p>
            </template>
          </el-form-item>
          <el-form-item
            :error="createValidation.errors.display_name"
            label="显示名"
            required
          >
            <el-input
              v-model="createForm.display_name"
              autocomplete="off"
              placeholder="页面上显示的姓名"
              :aria-invalid="Boolean(createValidation.errors.display_name)"
              aria-describedby="createForm-display_name-error"
            />
            <template #error>
              <p
                v-if="createValidation.errors.display_name"
                id="createForm-display_name-error"
                class="field-error"
                role="alert"
              >
                {{ createValidation.errors.display_name }}
              </p>
            </template>
          </el-form-item>
          <el-form-item label="电话">
            <el-input
              v-model="createForm.phone"
              autocomplete="off"
              inputmode="tel"
              maxlength="32"
              placeholder="11 位手机号，选填"
            />
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input
              v-model="createForm.email"
              autocomplete="off"
              inputmode="email"
              maxlength="254"
              placeholder="选填"
            />
          </el-form-item>
        </div>
        <el-form-item label="初始密码">
          <el-input
            v-model="createForm.password"
            type="password"
            show-password
            autocomplete="new-password"
            placeholder="留空则由系统生成"
          />
          <p class="field-hint">
            无论谁设置，用户首次登录都必须改成自己的密码。
          </p>
        </el-form-item>
        <el-form-item
          label="角色"
          class="create-roles"
        >
          <template v-if="canGrant">
            <RolePicker
              v-model="createRoles"
              :roles="allRoles"
              :disabled="creating"
            />
            <p class="field-hint">
              角色决定能用哪些模块，可多选；不确定时也可以先不选，之后在「待分配角色」里补。
            </p>
          </template>
          <template v-else>
            <p
              class="create-roles__note"
              role="note"
            >
              分配角色需要超级管理员。可以先建账号，它会出现在「待分配角色」里，超级管理员在那里能直接看到并分配。
            </p>
            <RolePicker
              v-if="allRoles.length"
              :model-value="[]"
              :roles="allRoles"
              disabled
            />
          </template>
        </el-form-item>
      </el-form>
      <template #footer>
        <span
          v-if="createGuard.dirty.value"
          class="editor-dirty"
          role="status"
        >有未保存的修改</span>
        <el-button
          :disabled="creating"
          @click="createGuard.close"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="creating"
          @click="onCreate"
        >
          创建
        </el-button>
      </template>
    </el-dialog>

    <UserDetailDrawer
      v-model="detailVisible"
      :user-id="detailUserId"
      :roles="allRoles"
      :can-edit="canEditUsers"
      :can-grant="canGrant"
      :can-audit="canAudit"
      @changed="onDetailChanged"
    />

    <PasswordOnceDialog
      v-model="onceVisible"
      :password="oncePassword"
      :username="onceUsername"
      @cleared="clearOnce"
    />
  </div>
</template>

<style scoped>
.muted {
  color: var(--zt-ink-500);
}

.user-link { font-weight: 500; }

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
  white-space: normal;
}

.role-cell :deep(.el-tag__content) {
  white-space: normal;
}

.status-text {
  margin-left: 6px;
  font-size: 12px;
  color: var(--zt-ink-500);
}

.pending-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  margin: 0 0 12px;
  padding: 8px 16px;
  border: 1px solid #f3dcb2;
  border-radius: var(--zt-radius);
  background: #fff8ec;
  color: #8a5a00;
  font-size: 13px;
}

.create-roles :deep(.el-form-item__content) {
  display: block;
}

/* 用户名、显示名都是短字段，并排放省一半高度。 */
.create-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 16px;
}

.field-hint,
.create-roles__note {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

.field-hint {
  color: var(--zt-ink-500);
}

.create-roles__note {
  color: var(--zt-ink-500);
}
</style>
