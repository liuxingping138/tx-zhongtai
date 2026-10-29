<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

import { errorMessage } from '@/api/errors'
import { listOnlineSessions, revokeOnlineSession } from '@/api/system'
import type { OnlineSession } from '@/api/types'
import ListEmpty from '@/components/ListEmpty.vue'
import ListPage from '@/components/ListPage.vue'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import UserAvatar from '../users/UserAvatar.vue'
import { browserOf, sinceText } from './loginText'

/** 在线用户：每台登录着的设备一行，可以单独下线。看跟着用户管理的查看权限，下线要用户管理可管理。 */
const auth = useAuthStore()
const canRevoke = computed(() => auth.canFull('system.users'))
const sessions = ref<OnlineSession[]>([])
const loading = ref(false)
const loadError = ref('')
const people = computed(() => new Set(sessions.value.map(item => item.user.id)).size)

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    sessions.value = (await listOnlineSessions()).items
  } catch (error) {
    loadError.value = errorMessage(error, '在线用户加载失败')
  } finally {
    loading.value = false
  }
}

async function revoke(item: OnlineSession): Promise<void> {
  const where = [browserOf(item.user_agent), item.ip].filter(Boolean).join('，')
  const sure = await ElMessageBox.confirm(
    `${item.user.display_name}（${item.user.username}）在这台设备（${where}）上会马上退出，其他设备不受影响。`,
    '下线这台设备',
    { type: 'warning', confirmButtonText: '下线', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!sure) return
  try {
    await revokeOnlineSession(item.id)
    ElMessage.success('已下线')
  } catch (error) {
    ElMessage.error(errorMessage(error, '下线失败'))
  }
  await load()
}

onMounted(load)
</script>

<template>
  <ListPage
    title="在线用户"
    hint="现在登录着的设备，一台一行。一个人在几台电脑或手机上登录就有几行。"
    :total="sessions.length"
    :page="1"
    :page-size="sessions.length || 1"
    :loading="loading"
    :error="loadError"
    hide-pager
    expanded-results
    @retry="load"
  >
    <template #actions>
      <span class="online-people">{{ people }} 人在线</span>
      <el-button
        :icon="Refresh"
        :loading="loading"
        @click="load"
      >
        刷新
      </el-button>
    </template>
    <el-table
      v-loading="loading"
      class="data-table"
      :data="sessions"
      stripe
    >
      <template #empty>
        <ListEmpty
          :loading="loading"
          :filtered="false"
        />
      </template>
      <el-table-column
        label="用户"
        min-width="240"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <span class="online-user">
            <UserAvatar :user="row.user" />
            <span class="online-user__name">{{ row.user.display_name }}</span>
            <span class="online-user__account">{{ row.user.username }}</span>
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="IP"
        width="160"
      >
        <template #default="{ row }">
          {{ row.ip || '—' }}
        </template>
      </el-table-column>
      <el-table-column
        label="浏览器 / 系统"
        min-width="170"
      >
        <template #default="{ row }">
          <span :title="row.user_agent">{{ browserOf(row.user_agent) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        label="登录时间"
        width="180"
      >
        <template #default="{ row }">
          <span :title="formatTime(row.created_at)">{{ sinceText(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        label="最近活跃"
        width="180"
      >
        <template #default="{ row }">
          <span :title="formatTime(row.last_seen_at)">{{ sinceText(row.last_seen_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        v-if="canRevoke"
        label="操作"
        width="100"
        fixed="right"
      >
        <template #default="{ row }">
          <el-button
            link
            type="danger"
            @click="revoke(row)"
          >
            下线
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </ListPage>
</template>

<style scoped>
.online-people { color: var(--zt-ink-500); font-size: 13px; }
.online-user { display: inline-flex; align-items: center; gap: 10px; max-width: 100%; vertical-align: middle; }
.online-user__name { color: var(--zt-ink-900); font-weight: 500; }
.online-user__account { overflow: hidden; color: var(--zt-ink-500); font-size: 13px; text-overflow: ellipsis; }
</style>
