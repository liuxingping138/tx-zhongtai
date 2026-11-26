<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { listAuditEvents } from '@/api/audit'
import { errorMessage } from '@/api/errors'
import { unlockLoginIp } from '@/api/system'
import type { AuditEventItem } from '@/api/types'
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import ListEmpty from '@/components/ListEmpty.vue'
import ListPage from '@/components/ListPage.vue'
import TableSkeleton from '@/components/TableSkeleton.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useListQuery } from '@/composables/useListQuery'
import { useAuthStore } from '@/stores/auth'
import { DEFAULT_RANGE_TIME, formatTime, toBeijingIso } from '@/utils/time'
import { browserOf, ipLimited, loginResult, normalizeIp } from './loginText'

/**
 * 登录日志：谁、什么时候、从哪个 IP 登录或退出，失败的写原因。数据就是操作日志里认证模块的那几类事件，
 * 权限跟着操作日志走。能对上账号的失败也记在这个人名下，按人筛看得到把他锁住的那些失败。
 * 来源 IP 输错太多次被暂时限制时，同一出口的人都登不上；超级管理员（有「权限分配」）可以在这里解除。
 */
const LOGIN_ACTIONS = ['login', 'logout', 'logout_all']
const IP_UNLOCK_NOTE = '同一出口可能有很多人，也可能是有人在试密码；确认是自己人输错了再解除。'

const auth = useAuthStore()
const canUnlockIp = computed(() => auth.canFull('system.permissions'))

const loading = ref(false)
const unlockingIp = ref('')
const loadError = ref('')
const resultFiltered = ref(false)
const events = ref<AuditEventItem[]>([])
const total = ref(0)
const query = reactive({
  actor_name: [] as string[],
  outcome: [] as string[],
  range: [] as string[] | null,
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/audit/events')
// 人名是个人信息，不写进地址栏（同操作日志页）。
const listQuery = useListQuery(query, load, ['actor_name'])
let loadSequence = 0

type LoginQuery = typeof query

function toRequest(params: LoginQuery) {
  return {
    page: params.page,
    page_size: params.page_size,
    module_code: ['auth'],
    action_code: LOGIN_ACTIONS,
    actor_name: params.actor_name,
    outcome: params.outcome,
    occurred_from: toBeijingIso(params.range?.[0]) || undefined,
    occurred_to: toBeijingIso(params.range?.[1]) || undefined,
  }
}

function isFiltered(params: LoginQuery): boolean {
  return Boolean(params.actor_name.length || params.outcome.length || params.range?.length)
}

async function load() {
  const params = listQuery.requested()
  void listQuery.commitPage()
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  try {
    const page = await listAuditEvents(toRequest(params))
    if (sequence !== loadSequence) return
    events.value = page.items
    total.value = page.total
    resultFiltered.value = isFiltered(params)
  } catch (error) {
    if (sequence === loadSequence) loadError.value = errorMessage(error, '登录日志加载失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function onSearch() {
  query.page = 1
  listQuery.captureApplied()
  void load()
}

function onReset() {
  query.actor_name = []
  query.outcome = []
  query.range = []
  onSearch()
}

async function unlockIp(ip: string): Promise<void> {
  if (unlockingIp.value) return
  unlockingIp.value = ip
  try {
    const result = await unlockLoginIp(ip)
    if (result.unlocked) ElMessage.success(`已解除 ${ip} 的登录限制，这个出口的人现在可以重新登录`)
    else ElMessage.info(`${ip} 现在没有被限制，可能已经到期自动解除`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '解除失败'))
  } finally {
    unlockingIp.value = ''
  }
}

/** 按这一行的来源 IP 解除。 */
async function unlockRow(row: AuditEventItem): Promise<void> {
  const ip = row.client_ip ?? ''
  const sure = await ElMessageBox.confirm(
    `解除后，从 ${ip} 来的登录马上可以重试。${IP_UNLOCK_NOTE}`,
    '解除 IP 登录限制',
    { type: 'warning', confirmButtonText: '解除', cancelButtonText: '取消' },
  ).then(() => true, () => false)
  if (sure) await unlockIp(ip)
}

/** 手填一个 IP 解除：同事说「登不上」时，问到对方的出口 IP 直接解，不必先翻到那一行。 */
async function promptUnlock(): Promise<void> {
  const answer = await ElMessageBox.prompt(
    `填被限制的来源 IP，就是登录日志里写「这个网络出口输错次数过多」那几行的 IP。${IP_UNLOCK_NOTE}`,
    '解除 IP 登录限制',
    {
      confirmButtonText: '解除',
      cancelButtonText: '取消',
      inputPlaceholder: '如 10.0.0.1',
      inputValidator: (value: string) => Boolean(normalizeIp(value ?? '')) || '请填写正确的 IP，如 10.0.0.1',
    },
  ).then(result => result.value, () => null)
  const ip = answer === null ? null : normalizeIp(answer)
  if (ip) await unlockIp(ip)
}

onMounted(() => {
  void load()
  void filters.load()
})
</script>

<template>
  <ListPage
    title="登录日志"
    hint="谁在什么时候、从哪里登录和退出；失败的写明原因。"
    :total="total"
    :page="query.page"
    :page-size="query.page_size"
    :loading="loading"
    :error="loadError"
    expanded-results
    @retry="load"
    @update:page="query.page = $event"
    @update:page-size="query.page_size = $event"
    @change="load"
  >
    <template
      v-if="canUnlockIp"
      #actions
    >
      <el-button
        :disabled="Boolean(unlockingIp)"
        @click="promptUnlock"
      >
        解除 IP 限制
      </el-button>
    </template>
    <template #filters>
      <FilterBar
        :query="query"
        :applied="listQuery.applied"
        @search="onSearch"
        @reset="onReset"
      >
        <el-form-item
          class="filter-form__item--wide"
          label="时间"
        >
          <el-date-picker
            v-model="query.range"
            type="datetimerange"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DDTHH:mm:ss"
            :default-time="DEFAULT_RANGE_TIME"
          />
        </el-form-item>
        <el-form-item label="账号">
          <FilterSelect
            v-model="query.actor_name"
            v-bind="filters.bind('actor_name')"
            placeholder="输入或选择人员"
          />
        </el-form-item>
        <el-form-item label="结果">
          <el-select
            v-model="query.outcome"
            multiple
            collapse-tags
            collapse-tags-tooltip
            clearable
            placeholder="全部"
          >
            <el-option
              label="成功"
              value="success"
            />
            <el-option
              label="失败"
              value="failure"
            />
          </el-select>
        </el-form-item>
      </FilterBar>
    </template>
    <TableSkeleton
      v-if="loading && events.length === 0"
      :rows="query.page_size || 10"
      :columns="canUnlockIp ? 6 : 5"
      :has-actions="canUnlockIp"
    />
    <el-table
      v-else
      class="data-table"
      :class="{ 'is-refreshing': loading }"
      :data="events"
      stripe
    >
      <template #empty>
        <ListEmpty
          :loading="loading"
          :filtered="resultFiltered"
          @reset="onReset"
        />
      </template>
      <el-table-column
        label="时间"
        width="190"
      >
        <template #default="{ row }">
          {{ formatTime(row.occurred_at) }}
        </template>
      </el-table-column>
      <el-table-column
        label="账号"
        min-width="200"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          {{ row.actor_name_snapshot || row.target_id || '—' }}
        </template>
      </el-table-column>
      <el-table-column
        label="结果"
        min-width="200"
      >
        <template #default="{ row }">
          <span :class="`login-result is-${loginResult(row).tone}`">{{ loginResult(row).text }}</span>
        </template>
      </el-table-column>
      <el-table-column
        label="IP"
        width="160"
      >
        <template #default="{ row }">
          {{ row.client_ip || '—' }}
        </template>
      </el-table-column>
      <el-table-column
        label="浏览器 / 系统"
        min-width="170"
      >
        <template #default="{ row }">
          <span :title="row.user_agent || ''">{{ browserOf(row.user_agent) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        v-if="canUnlockIp"
        label="操作"
        width="110"
        class-name="table-action"
      >
        <template #default="{ row }">
          <button
            v-if="ipLimited(row)"
            type="button"
            class="row-action row-action--primary"
            :disabled="Boolean(unlockingIp)"
            :aria-busy="Boolean(row.client_ip) && unlockingIp === row.client_ip"
            @click="unlockRow(row)"
          >
            {{ Boolean(row.client_ip) && unlockingIp === row.client_ip ? '解除中…' : '解除限制' }}
          </button>
        </template>
      </el-table-column>
    </el-table>
  </ListPage>
</template>

<style scoped>
.login-result.is-ok { color: var(--zt-success-text); }
.login-result.is-bad { color: var(--zt-danger-text); }
.login-result.is-plain { color: var(--zt-ink-500); }
</style>
