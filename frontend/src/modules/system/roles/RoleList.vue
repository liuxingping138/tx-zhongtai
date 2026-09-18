<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { createRole, listRoles, updateRole } from '@/api/system'
import { errorMessage, isApiError } from '@/api/errors'
import type { RoleItem } from '@/api/types'
import ListPage from '@/components/ListPage.vue'
import ListEmpty from '@/components/ListEmpty.vue'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const roles = ref<RoleItem[]>([])
const total = ref(0)
const query = reactive({ page: 1, page_size: 20, status: '' })
const createVisible = ref(false)
const creating = ref(false)
const createForm = reactive({ code: '', name: '' })
const editVisible = ref(false)
const editingSaving = ref(false)
const editing = ref<RoleItem | null>(null)
const editForm = reactive({ name: '' })

const createGuard = useUnsavedForm(createVisible, () => createForm, creating)
const editGuard = useUnsavedForm(editVisible, () => editForm, editingSaving)

function openCreate() {
  createForm.code = ''
  createForm.name = ''
  createVisible.value = true
}

let loadSequence = 0

async function load() {
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  const filtered = Object.entries(query).some(([key, value]) =>
    !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
  try {
    const page = await listRoles({
      page: query.page,
      page_size: query.page_size,
      status: query.status || undefined,
    })
    if (sequence !== loadSequence) return
    roles.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = errorMessage(error, '加载角色失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function onResetFilters() {
  query.status = ''
  onSearch()
}

function onSearch() {
  query.page = 1
  void load()
}

async function onCreate() {
  if (creating.value) return
  if (!createForm.code || !createForm.name) {
    ElMessage.warning('请填写编码和名称')
    return
  }
  creating.value = true
  try {
    await createRole({ code: createForm.code, name: createForm.name })
    ElMessage.success('角色已创建')
    createVisible.value = false
    createForm.code = ''
    createForm.name = ''
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '创建失败'))
  } finally {
    creating.value = false
  }
}

function openEdit(role: RoleItem) {
  editing.value = role
  editForm.name = role.name
  editVisible.value = true
}

async function onEdit() {
  if (editingSaving.value) return
  if (!editForm.name.trim()) {
    ElMessage.warning('请填写角色名称')
    return
  }
  if (!editing.value) {
    return
  }
  editingSaving.value = true
  try {
    await updateRole(editing.value.id, { name: editForm.name, version: editing.value.version })
    ElMessage.success('已保存')
    editVisible.value = false
    await load()
  } catch (error) {
    if (isApiError(error) && error.status === 409) {
      await ElMessageBox.alert('数据已被他人修改，请重新加载。', '版本冲突')
      await load()
    } else {
      ElMessage.error(errorMessage(error, '保存失败'))
    }
  } finally {
    editingSaving.value = false
  }
}

async function toggleStatus(role: RoleItem) {
  if (role.is_builtin) {
    ElMessage.warning('不能停用内置角色')
    return
  }
  const next = role.status === 'active' ? 'disabled' : 'active'
  const confirmed = await ElMessageBox.confirm(`确认${next === 'disabled' ? '停用' : '启用'}角色 ${role.name} ？`, '请确认', {
    type: 'warning',
  }).then(() => true, () => false)
  if (!confirmed) return
  try {
    await updateRole(role.id, { status: next, version: role.version })
    ElMessage.success('状态已更新')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error, '更新失败'))
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div>
    <ListPage
      title="角色管理"
      hint="维护团队角色，在权限分配中设置可访问的模块。"
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
        v-if="auth.canFull('system.roles')"
        #actions
      >
        <el-button
          type="primary"
          @click="openCreate"
        >
          新增角色
        </el-button>
      </template>
      <template #filters>
        <el-form
          class="filter-form"
          inline
          label-position="top"
        >
          <div class="filter-form__fields">
            <el-form-item label="状态">
              <el-select
                v-model="query.status"
                clearable
                placeholder="全部"
                @change="onSearch"
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
          </div>
          <el-form-item class="filter-form__submit">
            <el-button @click="onResetFilters">
              重置
            </el-button>
          </el-form-item>
        </el-form>
      </template>
      <el-table
        v-loading="loading"
        class="data-table"
        :data="roles"
        stripe
        border
      >
        <template #empty>
          <ListEmpty
            :loading="loading"
            :filtered="resultFiltered"
            @reset="onResetFilters"
          />
        </template>
        <el-table-column
          prop="code"
          label="编码"
        />
        <el-table-column
          prop="name"
          label="名称"
        />
        <el-table-column
          label="状态"
          width="100"
        >
          <template #default="{ row }">
            <el-tag
              :type="row.status === 'active' ? 'success' : 'info'"
              size="small"
            >
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="类型"
          width="90"
        >
          <template #default="{ row }">
            <el-tag
              v-if="row.is_builtin"
              size="small"
              type="warning"
              effect="plain"
            >
              内置
            </el-tag>
            <span
              v-else
              class="muted"
            >自定义</span>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="260"
        >
          <template #default="{ row }">
            <el-button
              v-if="auth.canFull('system.roles')"
              link
              type="primary"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="auth.canFull('system.roles') && !row.is_builtin"
              link
              type="primary"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>
            <el-button
              v-if="auth.canRead('system.permissions')"
              link
              type="primary"
              @click="router.push({ name: 'system-role-grants', params: { roleId: row.id } })"
            >
              配置权限
            </el-button>
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
      title="新增角色"
      width="420px"
    >
      <p class="editor-help">
        角色编码创建后不可修改，名称可随时调整。
      </p>
      <el-form
        :disabled="creating"
        label-position="top"
      >
        <el-form-item
          label="编码"
          required
        >
          <el-input v-model="createForm.code" />
        </el-form-item>
        <el-form-item
          label="名称"
          required
        >
          <el-input v-model="createForm.name" />
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
      title="编辑角色"
      width="420px"
    >
      <el-form
        :disabled="editingSaving"
        label-position="top"
      >
        <el-form-item
          label="名称"
          required
        >
          <el-input v-model="editForm.name" />
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
  </div>
</template>

<style scoped>
.muted {
  color: var(--zt-ink-500);
}
</style>
