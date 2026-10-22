<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'

import type { ScheduledRun } from '@/api/scheduler'
import ScrollPort from '@/components/ScrollPort.vue'
import { formatTime } from '@/utils/time'
import AiTaggingBilling from './AiTaggingBilling.vue'
import { formatYuan, runResultText, taskOfJob } from './aiTagging'
import { STATUS_TEXT, duration, statusType, type RunStatus } from './runStatus'
import type { SchedulerHistory } from './useSchedulerHistory'

const props = defineProps<{ history: SchedulerHistory }>()
// 历史记录状态在页面里只创建一次，拆成顶层 ref 后模板能直接解包。
const { job, visible, records, loading, error, page, total, load } = props.history
// 打标任务多一个「按天账单」页签；每次打开回到执行记录。
const task = computed(() => (job.value ? taskOfJob(job.value.code) : null))
const tab = ref<'runs' | 'billing'>('runs')
watch(visible, open => { if (open) tab.value = 'runs' })

function resultText(row: ScheduledRun): string {
  if (task.value) return runResultText(row.result)
  if (!row.result?.days_synced && row.result?.days_synced !== 0) return row.error_message || '—'
  return `处理 ${row.result.days_synced} 个采集日 · 网站快照 ${row.result.site_rows ?? '—'} 条`
}
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="`${job?.name ?? ''} · 执行记录`"
    size="min(1120px, 96vw)"
  >
    <el-tabs
      v-if="task"
      v-model="tab"
    >
      <el-tab-pane
        label="执行记录"
        name="runs"
      />
      <el-tab-pane
        label="按天账单"
        name="billing"
      />
    </el-tabs>
    <AiTaggingBilling
      v-if="task && tab === 'billing'"
      :key="task"
      :task="task"
    />
    <template v-else>
      <div class="history-toolbar">
        <span>共 {{ total }} 次执行 · 时间均为北京时间</span><el-button
          :loading="loading"
          :icon="Refresh"
          @click="load()"
        >
          刷新记录
        </el-button>
      </div>
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
        show-icon
      />
      <ScrollPort class="history-table">
        <el-table
          v-loading="loading"
          :data="records"
          row-key="id"
          :empty-text="loading ? '正在加载执行记录…' : '暂无执行记录，计划触发或手动执行后会在这里显示。'"
        >
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="run-detail">
                <p>执行编号：{{ row.id }}</p>
                <p>发起人：{{ row.actor_name }} · 原计划时间：{{ formatTime(row.scheduled_at) }}</p>
                <el-alert
                  v-if="row.error_message"
                  :title="row.error_message"
                  :type="row.status === 'failed' ? 'error' : 'warning'"
                  :closable="false"
                />
                <p v-if="row.status === 'retrying'">
                  下次重试：{{ formatTime(row.available_at) }}
                </p>
                <template v-if="row.result && task">
                  <p>{{ row.result.note || '—' }}</p>
                  <p>处理政策 {{ row.result.source_rows ?? 0 }} 条 · 费用 {{ formatYuan(row.result.cost) }}</p>
                  <p v-if="task === 'type'">
                    读取进度：{{ row.result.source_from || '—' }} → {{ row.result.source_to || '—' }}
                  </p>
                </template>
                <template v-else-if="row.result">
                  <p>处理日期：{{ row.result.date_from || '—' }} 至 {{ row.result.date_to || '—' }}</p>
                  <p>数据更新至：{{ formatTime(row.result.watermark) }}</p>
                  <p v-if="row.result.days_synced !== undefined">
                    已处理 {{ row.result.days_synced }} 个采集日 · 网站快照 {{ row.result.site_rows ?? '—' }} 条
                  </p>
                </template>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            label="触发方式"
            width="100"
          >
            <template #default="{ row }">
              {{ row.trigger === 'manual' ? '手动执行' : '每日计划' }}
            </template>
          </el-table-column>
          <el-table-column
            label="状态"
            width="110"
          >
            <template #default="{ row }">
              <el-tag
                :type="statusType(row.status)"
                size="small"
              >
                {{ STATUS_TEXT[row.status as RunStatus] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            label="入队时间"
            width="185"
          >
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column
            label="开始时间"
            width="185"
          >
            <template #default="{ row }">
              {{ formatTime(row.started_at) }}
            </template>
          </el-table-column>
          <el-table-column
            label="结束时间"
            width="185"
          >
            <template #default="{ row }">
              {{ formatTime(row.finished_at) }}
            </template>
          </el-table-column>
          <el-table-column
            label="总耗时"
            width="115"
          >
            <template #default="{ row }">
              {{ duration(row) }}
            </template>
          </el-table-column>
          <el-table-column
            prop="attempts"
            label="尝试次数"
            width="100"
          />
          <el-table-column
            label="结果"
            min-width="320"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              {{ resultText(row) }}
            </template>
          </el-table-column>
        </el-table>
      </ScrollPort>
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="prev, pager, next"
        @current-change="load()"
      />
    </template>
  </el-drawer>
</template>

<style scoped>
.history-toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; color: var(--zt-ink-500); font-size: 13px; }
.history-table { height: min(66vh, 650px); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); margin: 16px 0; }
.run-detail { padding: 8px 24px; color: var(--zt-ink-700); font-size: 13px; overflow-wrap: anywhere; }
.run-detail p { line-height: 1.7; }
</style>
