<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createUser,
  listRoles,
  listUsers,
  replaceUserRoles,
  resetUserPassword,
  revokeUserSessions,
  updateUser,
} from '@/api/system'
import { errorMessage, isApiError } from '@/api/errors'
import type { RoleItem, UserItem } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import ListPage from '@/components/ListPage.vue'
import PasswordOnceDialog from '@/components/PasswordOnceDialog.vue'

const auth = useAuthStore()
const loading = ref(false)
const users = ref<UserItem[]>([])
const total = ref(0)
const query = reactive({
  username: '',
  status: '',
  page: 1,
  page_size: 20,
})

const createVisible = ref(false)
const createForm = reactive({ username: '', display_name: '', password: '' })
const creating = ref(false)

const editVisible = ref(false)
const editing = ref<UserItem | null>(null)
const editForm = reactive({ display_name: '' })

const roleVisible = ref(false)
const roleUser = ref<UserItem | null>(null)
const roleOptions = ref<RoleItem[]>([])
const selectedRoles = ref<string[]>([])

const onceVisible = ref(false)
const oncePassword = ref('')
const onceUsername = ref('')

async function load() {
  loading.value = true
  try {
    const page = await listUsers({
      page: query.page,
      page_size: query.page_size,
      username: query.username || undefined,
      status: query.status || undefined,
    })
    users.value = page.items
    total.value = page.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载用户失败'))
  } finally {
    loading.value = false
  }
}

function onSearch() {
  query.page = 1
  void load()
}

async function onCreate() {
  if (!createForm.username || !createForm.display_name) {
    ElMessage.warning('请填写用户名和显示名')
    return
  }
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
    ElMessage.error(errorMessage(error, '创建失败'))
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
  if (!editing.value) {
    return
  }
  try {
    await updateUser(editing.value.id, { display_name: editForm.display_name, version: editing.value.version })
    ElMessage.success('已保存')
    editVisible.value = false
    await load()
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert('数据已被他人修改，请重新加载后再编辑。', '版本冲突')
      await load()
    } else {
      ElMessage.error(errorMessage(error, '保存失败'))
    }
  }
}

async function toggleStatus(user: UserItem) {
  const next = user.status === 'active' ? 'disabled' : 'active'
  const label = next === 'disabled' ? '禁用' : '启用'
  await ElMessageBox.confirm(`确认${label}用户 ${user.username} ？`, '请确认', { type: 'warning' })
  try {
    await updateUser(user.id, { status: next, version: user.version })
    ElMessage.success(`已${label}`)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, `${label}失败`))
  }
}

async function onReset(user: UserItem) {
  await ElMessageBox.confirm(`将重置 ${user.username} 的密码并强制其下次登录改密，是否继续？`, '重置密码', {
    type: 'warning',
  })
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
  await ElMessageBox.confirm(`确认强制下线 ${user.username} 的全部会话？`, '强制下线', { type: 'warning' })
  try {
    const result = await revokeUserSessions(user.id)
    ElMessage.success(`已撤销 ${result.revoked} 个会话`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '下线失败'))
  }
}

async function openRoles(user: UserItem) {
  roleUser.value = user
  const page = await listRoles({ page: 1, page_size: 100 })
  roleOptions.value = page.items
  selectedRoles.value = user.role_ids ?? []
  if (!user.role_ids) {
    const detail = await import('@/api/system').then((mod) => mod.getUser(user.id))
    selectedRoles.value = detail.role_ids ?? []
    roleUser.value = detail
  }
  roleVisible.value = true
}

async function onSaveRoles() {
  if (!roleUser.value) {
    return
  }
  try {
    await replaceUserRoles(roleUser.value.id, { role_ids: selectedRoles.value, version: roleUser.value.version })
    ElMessage.success('角色已更新')
    roleVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '分配角色失败'))
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

onMounted(() => {
  void load()
})
</script>

<template>
  <div>
    <ListPage
      title="用户管理"
      hint="管理登录账号。模块权限请在「权限分配」里配到角色上，再在这里把角色分给用户。"
      :total="total"
      :page="query.page"
      :page-size="query.page_size"
      :loading="loading"
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
          @click="createVisible = true"
        >
          新增用户
        </el-button>
      </template>
      <template #filters>
        <el-form
          class="filter-form"
          inline
          @submit.prevent="onSearch"
        >
          <el-form-item label="用户名">
            <el-input
              v-model="query.username"
              clearable
              placeholder="用户名"
            />
          </el-form-item>
          <el-form-item label="状态">
            <el-select
              v-model="query.status"
              clearable
              placeholder="全部"
              style="width: 140px"
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
          <el-form-item>
            <el-button
              native-type="submit"
              type="primary"
            >
              查询
            </el-button>
          </el-form-item>
        </el-form>
      </template>
      <el-table
        v-loading="loading"
        class="data-table"
        :data="users"
        stripe
        border
      >
        <el-table-column
          prop="username"
          label="用户名"
        />
        <el-table-column
          prop="display_name"
          label="显示名"
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
      title="新增用户"
      width="420px"
    >
      <el-form label-width="90px">
        <el-form-item
          label="用户名"
          required
        >
          <el-input v-model="createForm.username" />
        </el-form-item>
        <el-form-item
          label="显示名"
          required
        >
          <el-input v-model="createForm.display_name" />
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
        <el-button @click="createVisible = false">
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
      title="编辑用户"
      width="420px"
    >
      <el-form label-width="90px">
        <el-form-item
          label="显示名"
          required
        >
          <el-input v-model="editForm.display_name" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          @click="onEdit"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="roleVisible"
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
        :class="{ 'is-on': selectedRoles.includes(role.id) }"
        :disabled="role.status !== 'active' && !selectedRoles.includes(role.id)"
        @click="toggleRole(role.id)"
      >
        <el-checkbox :model-value="selectedRoles.includes(role.id)" />
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
        <el-button @click="roleVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
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
