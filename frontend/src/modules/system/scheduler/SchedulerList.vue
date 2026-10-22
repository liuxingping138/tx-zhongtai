<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { listAiTasks, type AiTask } from '@/api/aiTagging'
import { listJobs, triggerJob, type ScheduledJob, type SchedulerOverview } from '@/api/scheduler'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import ListPage from '@/components/ListPage.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import type { DataColumn } from '@/components/dataColumns'
import JobSettingsDrawer from './JobSettingsDrawer.vue'
import SchedulerHistoryDrawer from './SchedulerHistoryDrawer.vue'
import { TASK_INTRO, formatYuan, taskOfJob } from './aiTagging'
import { STATUS_TEXT, statusType, type RunStatus } from './runStatus'
import { useSchedulerHistory } from './useSchedulerHistory'

const auth = useAuthStore()
const canManage = computed(() => auth.canFull('system.scheduler'))
const overview = ref<SchedulerOverview | null>(null)
// 政策 AI 打标三个任务的设置、今天花费和进度，按调度编码对到任务行上。
const aiTasks = ref<AiTask[]>([])
const loading = ref(false)
const loadError = ref('')
const pending = ref('')
// 计划和下次时间、状态和结束时间各并成一列，六列在常见宽度下一屏放下。
const columns: DataColumn[] = [
  { prop: 'name', label: '任务名称', minWidth: 160 },
  { prop: 'plan', label: '每日计划', width: 190 },
  { prop: 'status', label: '最近执行', width: 210 },
  { prop: 'cost', label: '今日费用 / 上限', width: 150 },
  { prop: 'watermark', label: '数据进度', width: 180 },
]
const defaults = columns.map(col => col.prop)
const selected = ref([...defaults])
const visibleColumns = computed(() => columns.filter(col => selected.value.includes(col.prop)))
function aiTask(job: ScheduledJob): AiTask | null {
  return aiTasks.value.find(task => task.job_code === job.code) ?? null
}
/** 数据进度：爬虫是源数据入库时间；类型判断是读到的采集日；解读、市场机会按待办做，没有进度。 */
function progress(job: ScheduledJob): string {
  if (job.code === 'crawler') return formatTime(job.watermark)
  const task = aiTask(job)
  return task?.cursor_date ? `读到 ${task.cursor_date}` : '—'
}
function cost(job: ScheduledJob): string {
  const task = aiTask(job)
  return task ? `${formatYuan(task.spent_today)} / ${formatYuan(task.daily_cost_limit)}` : '—'
}
/** 「2026-10-22 17:01:10」只留月日时分，并在一列里放得下。 */
function short(value: string | null | undefined): string {
  const text = formatTime(value)
  return text.length >= 16 ? text.slice(5, 16) : text
}
/** 每日计划下面一行：启用时写下次什么时候跑。 */
function nextRun(job: ScheduledJob): string {
  return job.enabled && job.next_run_at ? `下次 ${short(job.next_run_at)}` : ''
}
/** 最近执行旁边一行：执行中的打标任务写模型答到第几条，结束了写结束时间。 */
function runNote(job: ScheduledJob): string {
  const current = job.active_run ? aiTask(job)?.current : null
  if (current) return current.total ? `${current.done ?? 0} / ${current.total} 条` : current.stage_name
  return job.last_run?.finished_at ? short(job.last_run.finished_at) : ''
}
function cell(job: ScheduledJob, prop: string) {
  if (prop === 'name') return job.name
  if (prop === 'cost') return cost(job)
  if (prop === 'watermark') return progress(job)
  return ''
}
let disposed = false
let loadSequence = 0
async function load(quiet = false) {
  if (loading.value) return
  loading.value = !quiet
  const current = ++loadSequence
  try {
    // 打标设置取不到（如 ai-service 维护）不影响看任务列表，保留上一次的数据。
    const [data, tasks] = await Promise.all([listJobs(), listAiTasks().catch(() => null)])
    if (!disposed && current === loadSequence) {
      overview.value = data
      if (tasks) aiTasks.value = tasks.items
      loadError.value = ''
    }
  } catch (e) {
    if (!disposed && current === loadSequence) loadError.value = errorMessage(e, '任务加载失败，请重试')
  } finally { if (current === loadSequence) loading.value = false }
}
async function execute(job: ScheduledJob) {
  if (pending.value) return
  const task = taskOfJob(job.code)
  const [message, title] = task
    ? [`${TASK_INTRO[task]}会产生模型费用，按这个任务的每日上限封顶。`, `立即执行一批「${job.name}」？`]
    : [`按上次成功水位补齐「${job.name}」的数据，不改变每日计划。`, '立即执行增量同步？']
  const ok = await ElMessageBox.confirm(message, title,
    { confirmButtonText: '开始执行', cancelButtonText: '取消', type: 'info' }).then(() => true, () => false)
  if (!ok) return
  pending.value = job.code
  try {
    await triggerJob(job.code)
    ElMessage.success('任务已加入队列，执行进程会自动处理')
    await load()
  } catch (e) { ElMessage.error(errorMessage(e, '提交失败')) }
  finally { pending.value = '' }
}
const settings = ref<InstanceType<typeof JobSettingsDrawer>>()
function edit(job: ScheduledJob) {
  settings.value?.open(job, aiTask(job))
}
const history = useSchedulerHistory()
let timer: ReturnType<typeof setTimeout> | undefined
async function poll() {
  if (!document.hidden) {
    await load(true)
    if (history.visible.value && !history.loading.value) await history.load(true)
  }
  if (!disposed) timer = setTimeout(() => { void poll() }, 5000)
}
onMounted(async () => { await load(); if (!disposed) timer = setTimeout(() => { void poll() }, 5000) })
onBeforeUnmount(() => { disposed = true; history.stop(); clearTimeout(timer) })
</script>

<template>
  <div class="scheduler-page">
    <div
      class="scheduler-strip"
      role="status"
    >
      <div>
        <el-tag
          :type="overview?.worker_online ? 'success' : 'warning'"
          effect="plain"
        >
          {{ !overview ? '正在检查调度状态' : overview.worker_online ? '自动调度运行中' : '执行进程离线' }}
        </el-tag>
        <span>每日按北京时间执行 · 自动补齐缺失增量</span>
      </div>
      <span v-if="overview?.heartbeat_at">最近心跳 {{ formatTime(overview.heartbeat_at) }}</span>
    </div>
    <el-alert
      v-if="overview && !overview.worker_online"
      title="执行进程暂未连接，任务将保留在队列中，恢复后自动处理。"
      type="warning"
      :closable="false"
      show-icon
    />
    <ListPage
      title="任务调度"
      :total="overview?.items.length ?? 0"
      :page="1"
      :page-size="20"
      hide-pager
      :loading="loading"
      :error="loadError"
      @retry="load()"
    >
      <template #tools>
        <el-button
          :icon="Refresh"
          :loading="loading"
          @click="load()"
        >
          刷新
        </el-button>
        <ColumnPicker
          v-model="selected"
          :columns="columns"
          :defaults="defaults"
        />
      </template>
      <el-table
        :data="overview?.items ?? []"
        class="data-table"
        row-key="code"
        :empty-text="loading ? '正在加载任务…' : '暂无任务，请联系管理员初始化任务配置'"
      >
        <el-table-column
          v-for="col in visibleColumns"
          :key="col.prop"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span
              v-if="col.prop === 'plan'"
              class="job-cell"
            >
              <el-tag
                :type="row.enabled ? 'success' : 'info'"
                size="small"
              >
                {{ row.enabled ? `每天 ${row.daily_time}` : '已停用' }}
              </el-tag>
              <span class="job-cell__note">{{ nextRun(row) }}</span>
            </span>
            <span
              v-else-if="col.prop === 'status'"
              class="job-cell"
            >
              <el-tag
                :type="statusType(row.last_run?.status)"
                size="small"
              >
                {{ row.last_run ? STATUS_TEXT[row.last_run.status as RunStatus] : '尚未执行' }}
              </el-tag>
              <span class="job-cell__note">{{ runNote(row) }}</span>
            </span>
            <span v-else>{{ cell(row, col.prop) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="220"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              v-if="canManage"
              link
              type="primary"
              :disabled="!!row.active_run || !!pending"
              :loading="pending === row.code"
              @click="execute(row)"
            >
              立即执行
            </el-button>
            <el-button
              v-if="canManage"
              link
              type="primary"
              @click="edit(row)"
            >
              设置
            </el-button>
            <el-button
              link
              type="primary"
              @click="history.open(row)"
            >
              执行记录
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </ListPage>
    <p class="scheduler-note">
      政策类型判断、政策解读、政策市场机会是三个独立任务：解读只做类型判断标为「是否解读 = 是」的政策，市场机会只做解读过的，前一步没跑后一步就没有待办。
      “数据进度”对爬虫是源数据的入库时间，对类型判断是源政策读到的采集日。失败后最多重试 2 次，分别等待 1 分钟、5 分钟；同一任务不会重复执行。
    </p>
    <JobSettingsDrawer
      ref="settings"
      @saved="load()"
    />
    <SchedulerHistoryDrawer :history="history" />
  </div>
</template>

<style scoped>
.scheduler-strip, .scheduler-strip > div { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.scheduler-strip { padding: 14px 16px; border: 1px solid var(--zt-border); background: var(--zt-panel); border-radius: var(--zt-radius); color: var(--zt-ink-500); font-size: 13px; }
.job-cell { display: inline-flex; align-items: center; gap: 8px; }
.job-cell__note { color: var(--zt-ink-500); font-size: 12px; font-variant-numeric: tabular-nums; }
.scheduler-note { color: var(--zt-ink-500); font-size: 13px; line-height: 1.8; margin: 16px 0; }
.scheduler-page :deep(.list-page) { min-height: 0; max-height: none; }
/* 任务只有四个：表格按内容撑开，不出内部滚动条。 */
.scheduler-page :deep(.list-page__results) { flex: none; min-height: 290px; }
</style>
