<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'

import { listAllRoles, listRoles, updateRole } from '@/api/system'
import { errorMessage } from '@/api/errors'
import type { RoleItem } from '@/api/types'
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import ListEmpty from '@/components/ListEmpty.vue'
import ListPage from '@/components/ListPage.vue'
import { useListQuery } from '@/composables/useListQuery'
import { roleModuleSummary } from '@/permissions/levels'
import { useAuthStore } from '@/stores/auth'
import RoleFormDialog, { type RoleFormMode } from './RoleFormDialog.vue'

/**
 * 角色列表。参考若依等后台的通行做法：列表只负责找到角色，每行给出「权限设置」「成员」两个主操作，
 * 具体配置在角色详情页完成，不在一个页面里同时列表又编辑。
 */
const auth = useAuthStore()
const router = useRouter()
const canManageRoles = computed(() => auth.canFull('system.roles'))
const canGrant = computed(() => auth.canFull('system.permissions'))

const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const roles = ref<RoleItem[]>([])
const total = ref(0)
const nameOptions = ref<string[]>([])
const query = reactive({ name: [] as string[], status: [] as string[], page: 1, page_size: 20 })
const listQuery = useListQuery(query, load)

const formVisible = ref(false)
const formMode = ref<RoleFormMode>('create')
const formRole = ref<RoleItem | null>(null)

let sequence = 0
async function load() {
  const params = listQuery.requested()
  void listQuery.commitPage()
  const current = ++sequence
  loading.value = true
  loadError.value = ''
  const filtered = params.name.length > 0 || params.status.length > 0
  try {
    const page = await listRoles({
      page: params.page,
      page_size: params.page_size,
      name: params.name.length ? params.name : undefined,
      status: params.status.length ? params.status : undefined,
    })
    if (current !== sequence) return
    roles.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (current !== sequence) return
    loadError.value = errorMessage(error, '暂时无法加载角色，请稍后重试。')
  } finally {
    if (current === sequence) loading.value = false
  }
}

async function loadNameOptions() {
  try {
    nameOptions.value = (await listAllRoles()).map(role => role.name)
  } catch {
    /* 候选取不到不影响列表，筛选框退化为自由输入。 */
  }
}

function onSearch() {
  query.page = 1
  listQuery.captureApplied()
  void load()
}

function onResetFilters() {
  query.name = []
  query.status = []
  onSearch()
}

function openDetail(role: RoleItem, tab: 'grants' | 'members' = 'grants') {
  void router.push({ name: 'system-role-detail', params: { roleId: role.id }, query: tab === 'members' ? { tab } : {} })
}

function openForm(mode: RoleFormMode, role: RoleItem | null = null) {
  formMode.value = mode
  formRole.value = role
  formVisible.value = true
}

async function onFormSaved(saved: RoleItem, mode: RoleFormMode) {
  if (mode === 'edit') {
    ElMessage.success('角色信息已保存')
    await load()
    return
  }
  // 新建或复制后直接进入权限设置，顺着「设置权限 → 分配成员」往下走。
  void loadNameOptions()
  void router.push({ name: 'system-role-detail', params: { roleId: saved.id }, query: { created: mode } })
}

async function onToggleStatus(role: RoleItem) {
  const next = role.status === 'active' ? 'disabled' : 'active'
  const members = role.member_count ?? 0
  const confirmed = await ElMessageBox.confirm(
    next === 'disabled'
      ? `停用后，${members} 位成员会立即失去这个角色带来的权限（其他角色不受影响），可随时重新启用。`
      : '启用后，成员会重新获得这个角色的权限。',
    `${next === 'disabled' ? '停用' : '启用'}「${role.name}」`,
    { type: 'warning', confirmButtonText: next === 'disabled' ? '停用' : '启用', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!confirmed) return
  try {
    await updateRole(role.id, { status: next, version: role.version })
    ElMessage.success(next === 'disabled' ? '角色已停用' : '角色已启用')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '操作失败'))
  }
}

function onMore(command: string, role: RoleItem) {
  if (command === 'edit') openForm('edit', role)
  else if (command === 'copy') openForm('copy', role)
  else if (command === 'toggle') void onToggleStatus(role)
}

function moduleSummary(role: RoleItem): string {
  return roleModuleSummary(role.grant_counts)
}

onMounted(() => {
  void load()
  void loadNameOptions()
})
</script>

<template>
  <div>
    <ListPage
      v-model:page="query.page"
      v-model:page-size="query.page_size"
      title="角色与权限"
      hint="角色决定一个人能进入哪些模块、能做什么。一个人可以有多个角色，权限取最高的那一档。"
      :loading="loading"
      :error="loadError"
      :total="total"
      @retry="load"
      @change="load"
    >
      <template
        v-if="canManageRoles"
        #actions
      >
        <el-button
          type="primary"
          @click="openForm('create')"
        >
          新增角色
        </el-button>
      </template>

      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          @search="onSearch"
          @reset="onResetFilters"
        >
          <el-form-item label="角色名称">
            <FilterSelect
              v-model="query.name"
              :options="nameOptions"
              placeholder="输入或选择角色名称"
            />
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

      <el-table
        v-loading="loading"
        class="data-table"
        :data="roles"
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
          label="角色名称"
          min-width="200"
        >
          <template #default="{ row }">
            <span class="role-name">
              <el-button
                link
                type="primary"
                class="role-name__link"
                @click="openDetail(row)"
              >
                {{ row.name }}
              </el-button>
              <el-tag
                v-if="row.is_builtin"
                size="small"
                type="warning"
                effect="plain"
              >
                内置
              </el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column
          label="职责说明"
          min-width="260"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span :class="{ muted: !row.description }">{{ row.description || '未填写' }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="权限"
          min-width="190"
        >
          <template #default="{ row }">
            <span v-if="moduleSummary(row)">{{ moduleSummary(row) }}</span>
            <span
              v-else
              class="warn"
            >还没有设置权限</span>
          </template>
        </el-table-column>
        <el-table-column
          label="成员"
          width="90"
          align="right"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              class="tabular"
              :aria-label="`${row.name}的成员：${row.member_count ?? 0} 人`"
              @click="openDetail(row, 'members')"
            >
              {{ row.member_count ?? 0 }} 人
            </el-button>
          </template>
        </el-table-column>
        <el-table-column
          label="状态"
          width="90"
        >
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.status === 'active' ? 'success' : 'info'"
            >
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="230"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="openDetail(row)"
            >
              权限设置
            </el-button>
            <el-button
              link
              type="primary"
              @click="openDetail(row, 'members')"
            >
              成员
            </el-button>
            <el-dropdown
              v-if="canManageRoles"
              class="ops-more"
              trigger="click"
              @command="(command: string) => onMore(command, row)"
            >
              <el-button
                link
                type="primary"
              >
                更多<el-icon class="el-icon--right">
                  <ArrowDown />
                </el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">
                    编辑名称和说明
                  </el-dropdown-item>
                  <el-dropdown-item
                    command="copy"
                    :disabled="!canGrant"
                  >
                    复制为新角色
                  </el-dropdown-item>
                  <el-dropdown-item
                    v-if="!row.is_builtin"
                    command="toggle"
                    divided
                  >
                    {{ row.status === 'active' ? '停用' : '启用' }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </ListPage>

    <RoleFormDialog
      v-model="formVisible"
      :mode="formMode"
      :role="formRole"
      @saved="onFormSaved"
    />
  </div>
</template>

<style scoped>
.role-name { display: inline-flex; align-items: center; gap: 6px; }
.role-name__link { font-weight: 500; }
.muted { color: var(--zt-ink-500); }
.warn { color: #b26a00; font-size: 13px; }
.tabular { font-variant-numeric: tabular-nums; }
.ops-more { margin-left: 12px; vertical-align: middle; }
</style>
