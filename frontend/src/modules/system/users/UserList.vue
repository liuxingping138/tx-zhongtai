<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'

import {
  createUser,
  listAllRoles,
  getUser,
  listUsers,
  replaceUserRoles,
  resetUserPassword,
  revokeUserSessions,
  updateUser,
} from '@/api/system'
import { errorMessage, isApiError } from '@/api/errors'
import type { RoleItem, UserItem } from '@/api/types'
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
const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const users = ref<UserItem[]>([])
const total = ref(0)
const query = reactive({
  username: '',
  status: '',
  page: 1,
  page_size: 20,
})
const usernameOptions = ref<string[]>([])

const createVisible = ref(false)
const createForm = reactive({ username: '', display_name: '', password: '' })
const creating = ref(false)

const editVisible = ref(false)
const editingSaving = ref(false)
const editing = ref<UserItem | null>(null)
const editForm = reactive({ display_name: '' })

const roleVisible = ref(false)
const roleLoading = ref(false)
const roleSaving = ref(false)
const roleUser = ref<UserItem | null>(null)
const roleOptions = ref<RoleItem[]>([])
const selectedRoles = ref<string[]>([])

const onceVisible = ref(false)
const oncePassword = ref('')
const onceUsername = ref('')

const createFormRef = ref<FormInstance>()
const editFormRef = ref<FormInstance>()
const createValidation = useFieldValidation(createForm, createFormRef)
const editValidation = useFieldValidation(editForm, editFormRef)

const createGuard = useUnsavedForm(createVisible, () => createForm, creating)
const editGuard = useUnsavedForm(editVisible, () => editForm, editingSaving)

function openCreate() {
  createForm.username = ''
  createForm.display_name = ''
  createForm.password = ''
  createVisible.value = true
}

const roleGuard = useUnsavedForm(roleVisible, () => [...selectedRoles.value].sort(), roleSaving)

const listQuery = useListQuery(query, load, ['username'])

let loadSequence = 0

async function load() {
  void listQuery.commit()
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  const filtered = Object.entries(query).some(([key, value]) =>
    !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
  try {
    const page = await listUsers({
      page: query.page,
      page_size: query.page_size,
      username: query.username || undefined,
      status: query.status || undefined,
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

function onResetFilters() {
  query.username = ''
  query.status = ''
  onSearch()
}

function onSearch() {
  query.page = 1
  void load()
}

const createError = ref('')
const editError = ref('')
watch(createVisible, (open) => { if (open) { createError.value = ''; void createValidation.validate({}) } })
watch(editVisible, (open) => { if (open) { editError.value = ''; void editValidation.validate({}) } })

async function onCreate() {
  if (creating.value) return
  createError.value = ''
  if (!await createValidation.validate({username: createForm.username.trim() ? '' : '请填写用户名', display_name: createForm.display_name.trim() ? '' : '请填写显示名'})) return
  creating.value = true
  try {
    const result = await createUser({
      username: createForm.username,
      display_name: createForm.display_name,
      password: createForm.password || undefined,
    })
    createVisible.value = false
    createForm.username = ''
    createForm.display_name = ''
    createForm.password = ''
    ElMessage.success('用户已创建')
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

function openEdit(user: UserItem) {
  editing.value = user
  editForm.display_name = user.display_name
  editVisible.value = true
}

async function onEdit() {
  if (editingSaving.value) return
  editError.value = ''
  if (!await editValidation.validate({ display_name: editForm.display_name.trim() ? '' : '请填写显示名' })) return
  if (!editing.value) {
    return
  }
  editingSaving.value = true
  try {
    await updateUser(editing.value.id, { display_name: editForm.display_name, version: editing.value.version })
    ElMessage.success('已保存')
    editVisible.value = false
    await load()
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      editError.value = '数据已被他人修改，请保留需要的内容，关闭后重新打开最新记录再编辑。'
      await load()
    } else {
      editError.value = errorMessage(error, '保存失败，请检查后重试')
    }
  } finally {
    editingSaving.value = false
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

async function openRoles(user: UserItem) {
  if (roleLoading.value || roleSaving.value) return
  roleLoading.value = true
  try {
    const [roles, detail] = await Promise.all([listAllRoles(), getUser(user.id)])
    roleOptions.value = roles
    roleUser.value = detail
    selectedRoles.value = [...(detail.role_ids ?? [])]
    roleVisible.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载用户角色失败'))
  } finally {
    roleLoading.value = false
  }
}

async function onSaveRoles() {
  if (!roleUser.value || roleSaving.value) {
    return
  }
  roleSaving.value = true
  try {
    await replaceUserRoles(roleUser.value.id, { role_ids: selectedRoles.value, version: roleUser.value.version })
    ElMessage.success('角色已更新')
    roleVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '分配角色失败'))
  } finally {
    roleSaving.value = false
  }
}

function toggleRole(roleId: string) {
  if (selectedRoles.value.includes(roleId)) {
    selectedRoles.value = selectedRoles.value.filter((id) => id !== roleId)
    return
  }
  selectedRoles.value = [...selectedRoles.value, roleId]
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
})
</script>

<template>
  <div>
    <ListPage
      title="用户管理"
      hint="管理登录账号、账号状态及角色分配。"
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
        v-if="auth.canFull('system.users')"
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
          <el-form-item label="状态">
            <el-select
              v-model="query.status"
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
              <el-option
                label="归档"
                value="archived"
              />
            </el-select>
          </el-form-item>
        </FilterBar>
      </template>
      <el-table
        v-loading="loading"
        class="data-table"
        :data="users"
        scrollbar-always-on
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
          prop="username"
          label="用户名"
          width="200"
          show-overflow-tooltip
        />
        <el-table-column
          prop="display_name"
          label="显示名"
          min-width="200"
          show-overflow-tooltip
        />
        <el-table-column
          label="状态"
          width="100"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.status === 'active' ? 'success' : row.status === 'disabled' ? 'warning' : 'info'"
              size="small"
            >
              {{ row.status === 'active' ? '启用' : row.status === 'disabled' ? '禁用' : '归档' }}
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
          v-if="auth.canFull('system.users') || auth.canFull('system.permissions')"
          label="操作"
          width="240"
        >
          <template #default="{ row }">
            <el-button
              v-if="auth.canFull('system.users')"
              link
              type="primary"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="auth.canFull('system.users')"
              link
              type="primary"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
            <el-button
              v-if="auth.canFull('system.permissions')"
              link
              type="primary"
              :disabled="roleLoading || roleSaving"
              @click="openRoles(row)"
            >
              分配角色
            </el-button>
            <el-dropdown
              v-if="auth.canFull('system.users')"
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
                  <el-dropdown-item @click="onReset(row)">
                    重置密码
                  </el-dropdown-item>
                  <el-dropdown-item @click="onRevoke(row)">
                    强制下线
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
      width="420px"
    >
      <p class="editor-help">
        用户名创建后不可修改；初始密码留空时由系统生成。
      </p>
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
        <el-form-item
          :error="createValidation.errors.username"
          label="用户名"
          required
        >
          <el-input
            v-model="createForm.username"
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
        <el-form-item label="初始密码">
          <el-input
            v-model="createForm.password"
            type="password"
            show-password
            placeholder="留空则系统生成"
          />
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

    <el-dialog
      v-model="editVisible"
      class="editor-overlay"
      :before-close="editGuard.beforeClose"
      :close-on-click-modal="!editingSaving"
      :close-on-press-escape="!editingSaving"
      :show-close="!editingSaving"
      title="编辑用户"
      width="420px"
    >
      <el-form
        ref="editFormRef"
        novalidate
        :disabled="editingSaving"
        label-position="top"
      >
        <el-alert
          v-if="editError"
          :title="editError"
          type="error"
          show-icon
          :closable="false"
          class="form-submit-error"
        />
        <el-form-item
          :error="editValidation.errors.display_name"
          label="显示名"
          required
        >
          <el-input
            v-model="editForm.display_name"
            :aria-invalid="Boolean(editValidation.errors.display_name)"
            aria-describedby="editForm-display_name-error"
          />
          <template #error>
            <p
              v-if="editValidation.errors.display_name"
              id="editForm-display_name-error"
              class="field-error"
              role="alert"
            >
              {{ editValidation.errors.display_name }}
            </p>
          </template>
        </el-form-item>
      </el-form>
      <template #footer>
        <span
          v-if="editGuard.dirty.value"
          class="editor-dirty"
          role="status"
        >有未保存的修改</span>
        <el-button
          :disabled="editingSaving"
          @click="editGuard.close"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="editingSaving"
          @click="onEdit"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="roleVisible"
      class="editor-overlay"
      :before-close="roleGuard.beforeClose"
      :close-on-click-modal="!roleSaving"
      :close-on-press-escape="!roleSaving"
      :show-close="!roleSaving"
      title="分配角色"
      size="440px"
    >
      <p class="role-drawer__hint">
        {{ roleUser?.display_name }}（{{ roleUser?.username }}）通过角色获得模块权限，不直接绑定资源。
      </p>
      <button
        v-for="role in roleOptions"
        :key="role.id"
        type="button"
        class="role-pick"
        :aria-pressed="selectedRoles.includes(role.id)"
        :class="{ 'is-on': selectedRoles.includes(role.id) }"
        :disabled="roleSaving || (role.status !== 'active' && !selectedRoles.includes(role.id))"
        @click="toggleRole(role.id)"
      >
        <span aria-hidden="true">{{ selectedRoles.includes(role.id) ? '☑' : '☐' }}</span>
        <span class="role-pick__text">
          <strong>{{ role.name }}</strong>
          <em>{{ role.code }}</em>
        </span>
        <el-tag
          :type="role.status === 'active' ? 'success' : 'info'"
          size="small"
        >
          {{ role.status === 'active' ? '启用' : '停用' }}
        </el-tag>
      </button>
      <template #footer>
        <span
          v-if="roleGuard.dirty.value"
          class="editor-dirty"
          role="status"
        >有未保存的修改</span>
        <el-button
          :disabled="roleSaving"
          @click="roleGuard.close"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="roleSaving"
          @click="onSaveRoles"
        >
          保存
        </el-button>
      </template>
    </el-drawer>

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

.role-drawer__hint {
  margin: 0 0 16px;
  color: var(--zt-ink-500);
  font-size: 13px;
  line-height: 1.5;
}

.role-pick {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  margin-bottom: 8px;
  padding: 12px;
  border: 1px solid var(--zt-border);
  border-radius: 6px;
  background: #fff;
  text-align: left;
  cursor: pointer;
}

.role-pick.is-on {
  background: #edf5ff;
  border-color: #c5dbf8;
}

.role-pick__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.role-pick__text strong {
  color: var(--zt-ink-900);
  font-size: 14px;
}

.role-pick__text em {
  color: var(--zt-ink-500);
  font-size: 12px;
  font-style: normal;
}
</style>
