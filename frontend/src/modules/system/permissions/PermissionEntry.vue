<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { listRoles } from '@/api/system'
import { errorMessage } from '@/api/errors'
import type { RoleItem } from '@/api/types'

const router = useRouter()
const loading = ref(false)
const roles = ref<RoleItem[]>([])

async function load() {
  loading.value = true
  try {
    const page = await listRoles({ page: 1, page_size: 100 })
    roles.value = page.items
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载角色失败'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <el-card>
    <h2>权限分配</h2>
    <p>选择一个角色，配置其已发布公共资源的 NONE / READ / FULL。未开发业务目录不可授权。</p>
    <el-table
      v-loading="loading"
      :data="roles"
    >
      <el-table-column
        prop="name"
        label="角色"
      />
      <el-table-column
        prop="code"
        label="编码"
      />
      <el-table-column
        prop="status"
        label="状态"
        width="100"
      />
      <el-table-column
        label="操作"
        width="140"
      >
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            @click="router.push({ name: 'system-role-grants', params: { roleId: row.id } })"
          >
            配置授权
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
