<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { NO_ROLE, importUsers, listAllRoles, listUsers } from '@/api/system'
import { errorMessage } from '@/api/errors'
import { reportImportResult, runExcelImport } from '@/api/excelImport'
import type { RoleItem, UserItem } from '@/api/types'
import ExportButton from '@/components/ExportButton.vue'
import FilterBar from '@/components/FilterBar.vue'
import ImportButton from '@/components/ImportButton.vue'
import ListPage from '@/components/ListPage.vue'
import PasswordOnceDialog from '@/components/PasswordOnceDialog.vue'
import { useExcelExport } from '@/composables/useExcelExport'
import { useListLoader } from '@/composables/useListLoader'
import { filtersForExport, useListQuery } from '@/composables/useListQuery'
import { useUserActions } from '@/composables/useUserActions'
import { useAuthStore } from '@/stores/auth'
import UserCreateDrawer from './UserCreateDrawer.vue'
import UserDetailDrawer from './UserDetailDrawer.vue'
import UserTable from './UserTable.vue'
import { mergeUserRow } from './userRows'

const auth = useAuthStore()
const router = useRouter()
/** 分配角色即授权，与后端同一门槛：需要「权限分配」可管理（只有超级管理员）。 */
const canGrant = computed(() => auth.canFull('system.permissions'))
const canReadRoles = computed(() => auth.canRead('system.roles'))
const canAudit = computed(() => auth.canRead('system.audit'))
const canEditUsers = computed(() => auth.canFull('system.users'))

const query = reactive({
  keyword: '',
  role_id: [] as string[],
  status: [] as string[],
  page: 1,
  page_size: 20,
})
const allRoles = ref<RoleItem[]>([])
/** 还没分配角色的账号数，给能分配角色的人一个入口直接筛出来。 */
const pendingCount = ref(0)

// 关键词可能是电话、邮箱，属于个人信息，不写进地址栏。
const listQuery = useListQuery(query, (): Promise<void> => load(), ['keyword'])
const { items, total, loading, loadError, resultFiltered, load } = useListLoader({
  requested: () => listQuery.requested(),
  commitPage: () => listQuery.commitPage(),
  fetch: (params) => {
    void loadPendingCount()
    return listUsers({
      page: params.page,
      page_size: params.page_size,
      keyword: params.keyword.trim() || undefined,
      role_id: params.role_id || undefined,
      status: params.status || undefined,
    })
  },
  errorText: '加载用户失败',
})

async function loadRoles() {
  if (!canReadRoles.value) return
  try {
    allRoles.value = await listAllRoles()
  } catch {
    /* 角色列表失败不影响用户列表；筛选退化为不可选，分配角色处会显示空列表。 */
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
  listQuery.search()
}

const IMPORT_HINT = '表头：用户名、显示名、电话、邮箱、角色。只新增不覆盖，已存在的用户名会跳过；'
  + '结果文件里有每个人的初始密码，只下载这一次。'

async function onImport(file: File) {
  try {
    const result = await runExcelImport(file, (onProgress) => importUsers(file, onProgress))
    result.report_note = result.inserted
      ? '结果文件已自动下载：「初始密码」页是新账号的初始密码，只给这一次，请发给本人，首次登录必须修改。'
        + (result.skipped ? '「跳过的行」页写了每行跳过的原因。' : '')
      : '结果文件已自动下载，「跳过的行」页写了每行跳过的原因。'
    reportImportResult(result, '用户导入结果.xlsx')
    if (result.inserted) await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '导入失败'))
  }
  return false
}

const { exporting, onExport } = useExcelExport({
  path: '/system/users/export',
  filename: '用户.xlsx',
  filters: () => filtersForExport(listQuery.applied),
})

// 密码只显示一次：重置密码和新建账号共用同一个弹窗。
const onceVisible = ref(false)
const oncePassword = ref('')
const onceUsername = ref('')

function showPassword(username: string, password: string) {
  onceUsername.value = username
  oncePassword.value = password
  onceVisible.value = true
}

function clearOnce() {
  oncePassword.value = ''
  onceUsername.value = ''
}

const createVisible = ref(false)
const detailVisible = ref(false)
const detailUserId = ref<string | null>(null)

function openCreate() {
  createVisible.value = true
  if (canGrant.value) void loadRoles()
}

function onCreated(result: { username: string; temporaryPassword: string | null }) {
  if (result.temporaryPassword) showPassword(result.username, result.temporaryPassword)
  void load()
}

function openDetail(user: UserItem) {
  detailUserId.value = user.id
  detailVisible.value = true
}

/** 详情里存好了：合进列表那一行（单独授权存好后「+单独授权」标签也跟着变），不整页重载。 */
function onDetailChanged(user: UserItem) {
  items.value = mergeUserRow(items.value, user)
  void loadRoles()
  void loadPendingCount()
  if (user.id === auth.user?.id) void auth.loadProfile()
}

function openAudit(user: UserItem) {
  void router.push({ name: 'system-audit', state: { auditActor: user.display_name } })
}

const actions = useUserActions({
  reload: load,
  showPassword,
  deleted: (userId) => {
    if (detailUserId.value === userId) detailVisible.value = false
  },
})

onMounted(() => {
  void load()
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
      <template #actions>
        <el-button
          v-if="canEditUsers"
          type="primary"
          @click="openCreate"
        >
          新增用户
        </el-button>
        <ImportButton
          v-if="canEditUsers"
          :hint="IMPORT_HINT"
          :upload="onImport"
        />
        <ExportButton
          :allowed="auth.canExport('system.users')"
          :loading="exporting"
          hint="按当前已生效的筛选条件导出，不含密码。导出的文件改好后可以直接当导入模板。"
          @click="onExport"
        />
      </template>
      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          @search="listQuery.search"
          @reset="listQuery.resetFilters"
        >
          <el-form-item label="关键词">
            <el-input
              v-model="query.keyword"
              clearable
              placeholder="用户名、姓名、电话或邮箱"
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
                label="停用"
                value="disabled"
              />
            </el-select>
          </el-form-item>
        </FilterBar>
      </template>
      <UserTable
        :users="items"
        :loading="loading"
        :filtered="resultFiltered"
        @open="openDetail"
        @toggle="actions.toggleStatus"
        @remove="actions.remove"
        @reset-password="actions.resetPassword"
        @revoke="actions.revokeSessions"
        @unlock="actions.unlock"
        @audit="openAudit"
        @reset="listQuery.resetFilters"
      />
    </ListPage>

    <UserCreateDrawer
      v-model="createVisible"
      :roles="allRoles"
      :can-grant="canGrant"
      @created="onCreated"
    />

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
.pending-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  margin: 0 0 12px;
  padding: 8px 16px;
  border: 1px solid var(--zt-warning-border);
  border-radius: var(--zt-radius);
  background: var(--zt-warning-soft);
  color: var(--zt-warning-text);
  font-size: 13px;
}
</style>
