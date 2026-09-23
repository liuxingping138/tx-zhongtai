<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { getAuditEvent, listAuditEvents } from '@/api/audit'
import { errorMessage } from '@/api/errors'
import FilterSelect from '@/components/FilterSelect.vue'
import ListPage from '@/components/ListPage.vue'
import FilterBar from '@/components/FilterBar.vue'
import { useFilterOptions } from '@/composables/useFilterOptions'
import { useListQuery } from '@/composables/useListQuery'
import ListEmpty from '@/components/ListEmpty.vue'
import type { AuditEventItem } from '@/api/types'
import { ACTION_LABELS, MODULE_LABELS, actionLabel, moduleLabel } from '@/utils/auditLabels'
import { formatTime, toBeijingIso } from '@/utils/time'

const loading = ref(false)
const loadError = ref('')
const resultFiltered = ref(false)
const events = ref<AuditEventItem[]>([])
const total = ref(0)
const query = reactive({
  actor_name: [] as string[],
  module_code: [] as string[],
  action_code: [] as string[],
  outcome: [] as string[],
  range: [] as string[] | null,
  page: 1,
  page_size: 20,
})
const filters = useFilterOptions('/audit/events')

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detail = ref<AuditEventItem | null>(null)

const outcomeLabel: Record<string, string> = {
  success: '成功',
  failure: '失败',
  denied: '拒绝',
}


const listQuery = useListQuery(query, load, ['actor_name'])

let loadSequence = 0

async function load() {
  void listQuery.commit()
  listQuery.captureApplied()
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  const filtered = Object.entries(query).some(([key, value]) =>
    !['page', 'page_size'].includes(key) && (Array.isArray(value) ? value.length > 0 : Boolean(value)),
  )
  try {
    const page = await listAuditEvents({
      page: query.page,
      page_size: query.page_size,
      actor_name: query.actor_name || undefined,
      module_code: query.module_code || undefined,
      action_code: query.action_code || undefined,
      outcome: query.outcome || undefined,
      occurred_from: toBeijingIso(query.range?.[0]) || undefined,
      occurred_to: toBeijingIso(query.range?.[1]) || undefined,
    })
    if (sequence !== loadSequence) return
    events.value = page.items
    total.value = page.total
    resultFiltered.value = filtered
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = errorMessage(error, '加载审计日志失败')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function onResetFilters() {
  query.actor_name = []
  query.module_code = []
  query.action_code = []
  query.outcome = []
  query.range = []
  onSearch()
}

function onSearch() {
  query.page = 1
  void load()
}

let detailSequence = 0

async function openDetail(row: AuditEventItem) {
  const sequence = ++detailSequence
  detailVisible.value = true
  detailLoading.value = true
  detailError.value = ''
  detail.value = row
  try {
    const result = await getAuditEvent(row.id)
    if (sequence === detailSequence) detail.value = result
  } catch (error) {
    if (sequence === detailSequence) detailError.value = errorMessage(error, '加载详情失败')
  } finally {
    if (sequence === detailSequence) detailLoading.value = false
  }
}

onMounted(() => {
  void load()
  void filters.load()
})
</script>

<template>
  <div>
    <ListPage
      title="操作日志"
      hint="查看操作记录，按时间、人员和模块追溯变更。"
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
      <template #filters>
        <FilterBar
          :query="query"
          :applied="listQuery.applied"
          @search="onSearch"
          @reset="onResetFilters"
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
          <el-form-item label="人员">
            <FilterSelect
              v-model="query.actor_name"
              v-bind="filters.bind('actor_name')"
              placeholder="输入或选择人员"
            />
          </el-form-item>
          <el-form-item label="模块">
            <FilterSelect
              v-model="query.module_code"
              v-bind="filters.bind('module_code')"
              :labels="MODULE_LABELS"
              placeholder="输入或选择模块"
            />
          </el-form-item>
          <template #advanced>
            <el-form-item label="动作">
              <FilterSelect
                v-model="query.action_code"
                v-bind="filters.bind('action_code')"
                :labels="ACTION_LABELS"
                placeholder="输入或选择动作"
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
                <el-option
                  label="拒绝"
                  value="denied"
                />
              </el-select>
            </el-form-item>
          </template>
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
            @reset="onResetFilters"
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
          prop="actor_name_snapshot"
          label="人员"
          width="120"
        />
        <el-table-column
          label="模块"
          width="140"
        >
          <template #default="{ row }">
            {{ moduleLabel(row.module_code) }}
          </template>
        </el-table-column>
        <el-table-column
          label="动作"
          width="100"
        >
          <template #default="{ row }">
            {{ actionLabel(row.action_code) }}
          </template>
        </el-table-column>
        <el-table-column
          label="结果"
          width="80"
        >
          <template #default="{ row }">
            {{ outcomeLabel[row.outcome] || row.outcome }}
          </template>
        </el-table-column>
        <el-table-column
          prop="summary"
          label="摘要"
          min-width="240"
        />
        <el-table-column
          label="操作"
          width="90"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="openDetail(row)"
            >
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </ListPage>
    <el-drawer
      v-model="detailVisible"
      title="审计详情"
      size="480px"
    >
      <el-alert
        v-if="detailError"
        type="error"
        :closable="false"
        show-icon
        :title="detailError"
      >
        <el-button
          v-if="detail"
          @click="openDetail(detail)"
        >
          重试
        </el-button>
      </el-alert>
      <el-skeleton
        v-if="detailLoading"
        :rows="8"
        animated
      />
      <el-descriptions
        v-else-if="detail"
        :column="1"
      >
        <el-descriptions-item label="时间">
          {{ formatTime(detail.occurred_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="人员">
          {{ detail.actor_name_snapshot || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="模块">
          {{ moduleLabel(detail.module_code) }}
        </el-descriptions-item>
        <el-descriptions-item label="动作">
          {{ actionLabel(detail.action_code) }}
        </el-descriptions-item>
        <el-descriptions-item label="结果">
          {{ outcomeLabel[detail.outcome] || detail.outcome }}
        </el-descriptions-item>
        <el-descriptions-item label="对象">
          {{ [detail.target_type, detail.target_id].filter(Boolean).join(' / ') || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="来源">
          {{ detail.source_service }}
        </el-descriptions-item>
        <el-descriptions-item label="摘要">
          {{ detail.summary || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="变更">
          <pre class="audit-json">{{ JSON.stringify(detail.changes, null, 2) }}</pre>
        </el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<style scoped>
.audit-json {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
}
</style>
