<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'

import { errorMessage } from '@/api/errors'
import {
  deleteIpWhitelist,
  getIpWhitelist,
  type IpWhitelistItem,
  type IpWhitelistOverview,
  type WhitelistUser,
} from '@/api/ipWhitelist'
import ListEmpty from '@/components/ListEmpty.vue'
import ListPage from '@/components/ListPage.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import IpWhitelistFormDialog from './IpWhitelistFormDialog.vue'
import { decisionText, remainingText } from './whitelistView'

/**
 * 访问白名单：智库只在公司网络能用。有人要在外面用，把被拦页面上显示的 IP 发给管理员，
 * 管理员在这里给他本人按 IP 开通、定有效期，到期自动失效。这一页本身不受网络限制。
 */
const auth = useAuthStore()
const canEdit = computed(() => auth.canFull('system.ip_whitelist'))
const overview = ref<IpWhitelistOverview | null>(null)
const loading = ref(false)
const loadError = ref('')
const deletingId = ref('')
const dialogOpen = ref(false)
const editing = ref<IpWhitelistItem | null>(null)
const presetUser = ref<WhitelistUser | null>(null)
const presetIp = ref('')

const rows = computed(() => overview.value?.items ?? [])
const current = computed(() => overview.value?.current ?? null)
const modules = computed(() => overview.value?.restricted_modules.join('、') || '智库')
const hint = computed(() => {
  if (!overview.value) return ''
  const office = overview.value.office_networks.join('、') || '未配置'
  return `${modules.value}只能在公司网络（${office}）下使用。其他地方要用的人，按他的账号和 IP 在这里开通，到期自动失效。`
})

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    overview.value = await getIpWhitelist()
  } catch (error) {
    loadError.value = errorMessage(error, '白名单加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate(user: WhitelistUser | null = null, ip = ''): void {
  editing.value = null
  presetUser.value = user
  presetIp.value = ip
  dialogOpen.value = true
}

function openEdit(item: IpWhitelistItem): void {
  editing.value = item
  presetUser.value = null
  presetIp.value = ''
  dialogOpen.value = true
}

async function remove(item: IpWhitelistItem): Promise<void> {
  if (deletingId.value) return
  const sure = await ElMessageBox.confirm(
    `删除后 ${item.user.display_name} 从 ${item.ip_range} 马上不能再使用${modules.value}（在公司网络里不受影响）。`,
    '删除白名单',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (!sure) return
  deletingId.value = item.id
  try {
    await deleteIpWhitelist(item.id)
    ElMessage.success('已删除')
  } catch (error) {
    ElMessage.error(errorMessage(error, '删除失败'))
  } finally {
    deletingId.value = ''
  }
  await load()
}

onMounted(load)
</script>

<template>
  <ListPage
    title="访问白名单"
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
    <template
      v-if="current"
      #summary
    >
      <div
        class="whitelist-current"
        :class="{ 'is-denied': !current.allowed }"
        role="status"
      >
        <span class="whitelist-current__text">{{ decisionText(current, modules) }}</span>
        <el-button
          v-if="canEdit && !current.allowed && current.ip"
          size="small"
          @click="openCreate(current.user, current.ip)"
        >
          给自己开通这个 IP
        </el-button>
      </div>
    </template>
    <template #actions>
      <el-button
        v-if="canEdit"
        type="primary"
        :icon="Plus"
        @click="openCreate()"
      >
        开通白名单
      </el-button>
      <el-button
        :icon="Refresh"
        :loading="loading"
        @click="load"
      >
        刷新
      </el-button>
    </template>
    <TableSkeleton
      v-if="loading && rows.length === 0"
      :columns="6"
      :has-actions="canEdit"
    />
    <el-table
      v-else
      class="data-table"
      :class="{ 'is-refreshing': loading }"
      :data="rows"
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
        min-width="180"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <span class="whitelist-user">{{ row.user.display_name }}</span>
          <span class="whitelist-account">{{ row.user.username }}</span>
        </template>
      </el-table-column>
      <el-table-column
        label="IP 地址"
        width="180"
        prop="ip_range"
      />
      <el-table-column
        label="状态"
        width="130"
      >
        <template #default="{ row }">
          <span :class="row.active ? 'whitelist-state is-active' : 'whitelist-state'">
            {{ row.active ? remainingText(row.expires_at) : '已过期' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="到期时间"
        width="170"
        prop="expires_at"
      />
      <el-table-column
        label="开通原因"
        min-width="180"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          {{ row.reason || '—' }}
        </template>
      </el-table-column>
      <el-table-column
        label="开通人"
        width="110"
        prop="created_by_name"
        show-overflow-tooltip
      />
      <el-table-column
        label="最后修改"
        width="170"
      >
        <template #default="{ row }">
          <span :title="`${row.updated_by_name} ${row.updated_at}`">{{ row.updated_at }}</span>
        </template>
      </el-table-column>
      <el-table-column
        v-if="canEdit"
        label="操作"
        width="150"
        class-name="table-action"
      >
        <template #default="{ row }">
          <button
            type="button"
            class="row-action"
            @click="openEdit(row)"
          >
            {{ row.active ? '修改' : '续期' }}
          </button>
          <button
            type="button"
            class="row-action row-action--danger"
            :disabled="Boolean(deletingId)"
            @click="remove(row)"
          >
            {{ deletingId === row.id ? '删除中…' : '删除' }}
          </button>
        </template>
      </el-table-column>
    </el-table>
    <IpWhitelistFormDialog
      v-model="dialogOpen"
      :item="editing"
      :preset-user="presetUser"
      :preset-ip="presetIp"
      :max-days="overview?.max_days ?? 365"
      @saved="load"
    />
  </ListPage>
</template>

<style scoped>
.whitelist-current {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--zt-success-border);
  border-radius: 8px;
  background: var(--zt-success-soft);
  color: var(--zt-success-text);
  font-size: 13px;
}
.whitelist-current.is-denied {
  border-color: var(--zt-warning-border);
  background: var(--zt-warning-soft);
  color: var(--zt-warning-text);
}
.whitelist-current__text { flex: 1; }
.whitelist-user { color: var(--zt-ink-900); font-weight: 550; }
.whitelist-account { margin-left: 8px; color: var(--zt-ink-500); font-size: 13px; }
.whitelist-state { display: inline-flex; align-items: center; gap: 6px; color: var(--zt-ink-500); font-size: 13px; }
.whitelist-state::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--zt-muted-mark); }
.whitelist-state.is-active { color: var(--zt-success-text); font-weight: 500; }
.whitelist-state.is-active::before { background: var(--zt-success); }
.is-refreshing {
  opacity: 0.65;
  pointer-events: none;
  transition: opacity 0.2s ease;
}
</style>
