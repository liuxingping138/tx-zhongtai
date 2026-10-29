<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { listAuditEvents } from '@/api/audit'
import { errorMessage } from '@/api/errors'
import type { AuditEventItem } from '@/api/types'
import FilterBar from '@/components/FilterBar.vue'
import FilterSelect from '@/components/FilterSelect.vue'
import ListEmpty from '@/components/ListEmpty.vue'
import ListPage from '@/components/ListPage.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useListQuery } from '@/composables/useListQuery'
import { formatTime, toBeijingIso } from '@/utils/time'
import { browserOf, loginResult } from './loginText'

/**
 * 登录日志：谁、什么时候、从哪个 IP 登录或退出，失败的写原因。数据就是操作日志里认证模块的那几类事件，
 * 权限跟着操作日志走。
 */
const LOGIN_ACTIONS = ['login', 'logout', 'logout_all']

const loading = ref(false)
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
const listQuery = useListQuery(query, load)
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
    <el-table
      v-loading="loading"
      class="data-table"
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
          {{ row.actor_name_snapshot || '—' }}
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
    </el-table>
  </ListPage>
</template>

<style scoped>
.login-result.is-ok { color: var(--zt-success-text); }
.login-result.is-bad { color: var(--zt-danger-text); }
.login-result.is-plain { color: var(--zt-ink-500); }
</style>
