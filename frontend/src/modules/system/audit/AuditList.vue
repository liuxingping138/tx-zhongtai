<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

import { auditFilterOptions, getAuditEvent, listAuditEvents } from '@/api/audit'
import { errorMessage } from '@/api/errors'
import FilterSelect from '@/components/FilterSelect.vue'
import ListPage from '@/components/ListPage.vue'
import type { AuditEventItem } from '@/api/types'
import { ACTION_LABELS, MODULE_LABELS, actionLabel, moduleLabel } from '@/utils/auditLabels'
import { formatTime } from '@/utils/time'

const route = useRoute()
const loading = ref(false)
const events = ref<AuditEventItem[]>([])
const total = ref(0)
const query = reactive({
  actor_name: '',
  module_code: '',
  action_code: '',
  outcome: '',
  range: [] as string[],
  page: 1,
  page_size: 20,
})
const options = reactive({
  actor_name: [] as string[],
  module_code: [] as string[],
  action_code: [] as string[],
})

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<AuditEventItem | null>(null)

const outcomeLabel: Record<string, string> = {
  success: '成功',
  failure: '失败',
  denied: '拒绝',
}

async function loadOptions() {
  try {
    const data = await auditFilterOptions()
    options.actor_name = data.actor_name ?? []
    options.module_code = data.module_code ?? []
    options.action_code = data.action_code ?? []
  } catch {
    /* 选项失败不影响列表 */
  }
}

async function load() {
  loading.value = true
  try {
    const page = await listAuditEvents({
      page: query.page,
      page_size: query.page_size,
      actor_name: query.actor_name || undefined,
      module_code: query.module_code || undefined,
      action_code: query.action_code || undefined,
      outcome: query.outcome || undefined,
      occurred_from: query.range[0] || undefined,
      occurred_to: query.range[1] || undefined,
    })
    events.value = page.items
    total.value = page.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载审计日志失败'))
  } finally {
    loading.value = false
  }
}

function onSearch() {
  query.page = 1
  void load()
}

async function openDetail(row: AuditEventItem) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = row
  try {
    detail.value = await getAuditEvent(row.id)
  } catch (error) {
    ElMessage.error(errorMessage(error, '加载详情失败'))
  } finally {
    detailLoading.value = false
  }
}

onMounted(() => {
  const moduleCode = route.query.module_code
  if (typeof moduleCode === 'string') {
    query.module_code = moduleCode
  }
  void load()
  void loadOptions()
})
</script>

<template>
  <div>
    <ListPage
      title="操作日志"
      hint="记录各模块的新增、编辑、导入等操作，可按时间、人员、模块筛选。"
      :total="total"
      :page="query.page"
      :page-size="query.page_size"
      :loading="loading"
      @update:page="query.page = $event"
      @update:page-size="query.page_size = $event"
      @change="load"
    >
      <template #filters>
        <el-form
          class="filter-form"
          inline
          label-position="top"
          @submit.prevent="onSearch"
        >
          <div class="filter-form__fields">
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
                :options="options.actor_name"
                placeholder="输入或选择人员"
              />
            </el-form-item>
            <el-form-item label="模块">
              <FilterSelect
                v-model="query.module_code"
                :options="options.module_code"
                :labels="MODULE_LABELS"
                placeholder="输入或选择模块"
              />
            </el-form-item>
            <el-form-item label="动作">
              <FilterSelect
                v-model="query.action_code"
                :options="options.action_code"
                :labels="ACTION_LABELS"
                placeholder="输入或选择动作"
              />
            </el-form-item>
            <el-form-item label="结果">
              <el-select
                v-model="query.outcome"
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
          </div>
          <el-form-item class="filter-form__submit">
            <el-button
              native-type="submit"
              type="primary"
            >
              查询
            </el-button>
          </el-form-item>
        </el-form>
      </template>
      <el-table
        v-loading="loading"
        class="data-table"
        :data="events"
        stripe
        border
      >
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
          width="140"
        />
        <el-table-column
          label="模块"
          width="160"
        >
          <template #default="{ row }">
            {{ moduleLabel(row.module_code) }}
          </template>
        </el-table-column>
        <el-table-column
          label="动作"
          width="140"
        >
          <template #default="{ row }">
            {{ actionLabel(row.action_code) }}
          </template>
        </el-table-column>
        <el-table-column
          label="结果"
          width="90"
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
      <el-skeleton
        v-if="detailLoading"
        :rows="8"
        animated
      />
      <el-descriptions
        v-else-if="detail"
        :column="1"
        border
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
