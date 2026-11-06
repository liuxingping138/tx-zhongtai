<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

import { errorMessage } from '@/api/errors'
import { listOnlineSessions, revokeOnlineSession, type OnlineDevice } from '@/api/system'
import ListEmpty from '@/components/ListEmpty.vue'
import ListPage from '@/components/ListPage.vue'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import UserAvatar from '../users/UserAvatar.vue'
import { browserOf, sinceText } from './loginText'
import { deviceAction, sessionCounts, visibleSessions, windowText, type SessionView } from './sessionView'

/**
 * 在线用户：每台设备一行。「在线」是最近 30 分钟内有操作的设备；「有效登录」是没退出、没过期的全部设备
 * （登录后 7 天内都有效），可能早就没在用了。看跟着用户管理的查看权限，下线要用户管理可管理；
 * 正在用的这台标「当前设备」、不给下线，要退出用「退出登录」。
 */
const auth = useAuthStore()
const canRevoke = computed(() => auth.canFull('system.users'))
const sessions = ref<OnlineDevice[]>([])
const windowSeconds = ref(1800)
const view = ref<SessionView>('online')
const loading = ref(false)
const loadError = ref('')
const counts = computed(() => sessionCounts(sessions.value))
const rows = computed(() => visibleSessions(sessions.value, view.value))
const windowLabel = computed(() => windowText(windowSeconds.value))
const hint = computed(() =>
  `在线：最近 ${windowLabel.value}内有操作的设备。有效登录：登录后没退出、没过期的全部设备（7 天内有效），可能早就没在用了。`,
)

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const result = await listOnlineSessions()
    sessions.value = result.items
    windowSeconds.value = result.online_window_seconds
  } catch (error) {
    loadError.value = errorMessage(error, '在线用户加载失败')
  } finally {
    loading.value = false
  }
}

async function revoke(item: OnlineDevice): Promise<void> {
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
    :hint="hint"
    :total="rows.length"
    :page="1"
    :page-size="rows.length || 1"
    :loading="loading"
    :error="loadError"
    hide-pager
    expanded-results
    @retry="load"
  >
    <template #actions>
      <el-radio-group
        v-model="view"
        aria-label="显示哪些设备"
      >
        <el-radio-button
          value="online"
          :title="`最近 ${windowLabel}内有操作`"
        >
          在线 {{ counts.onlinePeople }} 人
        </el-radio-button>
        <el-radio-button
          value="all"
          title="登录后没退出、没过期的全部设备（7 天内有效），可能早就没在用了"
        >
          有效登录 {{ counts.validPeople }} 人
        </el-radio-button>
      </el-radio-group>
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
      :data="rows"
      stripe
    >
      <template #empty>
        <!-- 只看在线时没人：当作筛过了，「清除筛选」切到全部有效登录。 -->
        <ListEmpty
          :loading="loading"
          :filtered="view === 'online' && sessions.length > 0"
          @reset="view = 'all'"
        />
      </template>
      <el-table-column
        label="用户"
        min-width="260"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <span class="online-user">
            <UserAvatar :user="row.user" />
            <span class="online-user__name">{{ row.user.display_name }}</span>
            <span class="online-user__account">{{ row.user.username }}</span>
            <el-tag
              v-if="row.current"
              size="small"
              effect="plain"
            >
              当前设备
            </el-tag>
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="状态"
        width="100"
      >
        <template #default="{ row }">
          <span :class="row.online ? 'online-state is-online' : 'online-state'">{{ row.online ? '在线' : '不在线' }}</span>
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
        width="110"
        fixed="right"
      >
        <template #default="{ row }">
          <span
            v-if="deviceAction(row, canRevoke) === 'current'"
            class="online-muted"
            title="这是你正在用的设备，要退出请点左下角账号里的「退出登录」"
          >正在使用</span>
          <button
            v-else-if="deviceAction(row, canRevoke) === 'revoke'"
            type="button"
            class="row-action row-action--danger"
            @click="revoke(row)"
          >
            下线
          </button>
          <span
            v-else
            class="online-muted"
            title="超级管理员的设备只有超级管理员能下线"
          >—</span>
        </template>
      </el-table-column>
    </el-table>
  </ListPage>
</template>

<style scoped>
.online-user { display: inline-flex; align-items: center; gap: 10px; max-width: 100%; vertical-align: middle; }
.online-user__name { color: var(--zt-ink-900); font-weight: 550; }
.online-user__account { overflow: hidden; color: var(--zt-ink-500); font-size: 13px; text-overflow: ellipsis; }
.online-state { display: inline-flex; align-items: center; gap: 6px; color: var(--zt-ink-500); font-size: 13px; }
.online-state::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--zt-muted-mark); }
.online-state.is-online { color: var(--zt-success-text); font-weight: 500; }
.online-state.is-online::before { background: var(--zt-success); }
.online-muted { color: var(--zt-ink-400); font-size: 12px; }
</style>
