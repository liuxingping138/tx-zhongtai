<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { createRole, listRoles, updateRole } from '@/api/system'
import { errorMessage, isApiError } from '@/api/errors'
import type { RoleItem } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const roles = ref<RoleItem[]>([])
const total = ref(0)
const query = reactive({ page: 1, page_size: 20, status: '' })
const createVisible = ref(false)
const creating = ref(false)
const createForm = reactive({ code: '', name: '' })
const editVisible = ref(false)
const editing = ref<RoleItem | null>(null)
const editForm = reactive({ name: '' })

async function load() {
  loading.value = true
  try {
    const page = await listRoles({
      page: query.page,
      page_size: query.page_size,
      status: query.status || undefined,
    })
    roles.value = page.items
    total.value = page.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载角色失败'))
  } finally {
    loading.value = false
  }
}

async function onCreate() {
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
  if (!editing.value) {
    return
  }
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
  }
}

async function toggleStatus(role: RoleItem) {
  if (role.is_builtin) {
    ElMessage.warning('不能停用内置角色')
    return
  }
  const next = role.status === 'active' ? 'disabled' : 'active'
  await ElMessageBox.confirm(`确认${next === 'disabled' ? '停用' : '启用'}角色 ${role.name} ？`, '请确认', {
    type: 'warning',
  })
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
    <el-form inline>
      <el-form-item label="状态">
        <el-select
          v-model="query.status"
          clearable
          placeholder="全部"
          style="width: 140px"
          @change="load"
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
      <el-form-item>
        <el-button
          v-if="auth.canFull('system.roles')"
          type="primary"
          @click="createVisible = true"
        >
          新增角色
        </el-button>
      </el-form-item>
    </el-form>
    <el-table
      v-loading="loading"
      :data="roles"
    >
      <el-table-column
        prop="code"
        label="编码"
      />
      <el-table-column
        prop="name"
        label="名称"
      />
      <el-table-column
        prop="status"
        label="状态"
        width="100"
      />
      <el-table-column
        label="内置"
        width="80"
      >
        <template #default="{ row }">
          {{ row.is_builtin ? '是' : '否' }}
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
    <el-pagination
      v-model:current-page="query.page"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 16px"
      @current-change="load"
    />

    <el-dialog
      v-model="createVisible"
      title="新增角色"
      width="420px"
    >
      <el-form label-width="80px">
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
      title="编辑角色"
      width="420px"
    >
      <el-form label-width="80px">
        <el-form-item
          label="名称"
          required
        >
          <el-input v-model="editForm.name" />
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
  </div>
</template>
