<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { listJobs, listRuns, triggerJob, updateJob, type ScheduledJob, type ScheduledRun, type SchedulerOverview } from '@/api/scheduler'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import ListPage from '@/components/ListPage.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import ScrollPort from '@/components/ScrollPort.vue'
import type { DataColumn } from '@/components/dataColumns'

const auth = useAuthStore()
const canManage = computed(() => auth.canFull('system.scheduler'))
const overview = ref<SchedulerOverview | null>(null)
const loading = ref(false)
const loadError = ref('')
const pending = ref('')
const columns: DataColumn[] = [
  { prop: 'name', label: '任务名称', minWidth: 230 },
  { prop: 'enabled', label: '每日计划', width: 100 },
  { prop: 'daily_time', label: '执行时刻', width: 110 },
  { prop: 'status', label: '最近状态', width: 120 },
  { prop: 'finished_at', label: '最近结束时间', width: 190 },
  { prop: 'watermark', label: '数据更新至', width: 190 },
  { prop: 'next_run_at', label: '下次计划时间', width: 190 },
]
const defaults = columns.map(col => col.prop)
const selected = ref([...defaults])
const visibleColumns = computed(() => columns.filter(col => selected.value.includes(col.prop)))
const statusText: Record<ScheduledRun['status'], string> = {
  queued: '排队中', running: '执行中', retrying: '等待重试', success: '成功', failed: '失败', cancelled: '已取消',
}
function statusType(status?: ScheduledRun['status']) {
  return status === 'success' ? 'success' : status === 'failed' ? 'danger' : status === 'retrying' ? 'warning' : 'info'
}
function cell(job: ScheduledJob, prop: string) {
  if (prop === 'name') return job.name
  if (prop === 'daily_time') return job.daily_time
  if (prop === 'finished_at') return formatTime(job.last_run?.finished_at)
  if (prop === 'watermark') return formatTime(job.watermark)
  if (prop === 'next_run_at') return formatTime(job.next_run_at)
  return ''
}
let disposed = false
let loadSequence = 0
async function load(quiet = false) {
  if (loading.value) return
  loading.value = !quiet
  const current = ++loadSequence
  try {
    const data = await listJobs()
    if (!disposed && current === loadSequence) { overview.value = data; loadError.value = '' }
  } catch (e) {
    if (!disposed && current === loadSequence) loadError.value = errorMessage(e, '任务加载失败，请重试')
  } finally { if (current === loadSequence) loading.value = false }
}
async function execute(job: ScheduledJob) {
  if (pending.value) return
  const ok = await ElMessageBox.confirm(`按上次成功水位补齐「${job.name}」的数据，不改变每日计划。`, '立即执行增量同步？',
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
const editing = ref<ScheduledJob | null>(null)
const dialog = ref(false)
const saving = ref(false)
const formError = ref('')
const form = reactive({ enabled: true, daily_time: '10:00', version: 1 })
const unsaved = useUnsavedForm(dialog, () => form, saving)
function edit(job: ScheduledJob) {
  editing.value = job
  Object.assign(form, { enabled: job.enabled, daily_time: job.daily_time, version: job.version })
  formError.value = ''
  dialog.value = true
}
async function save() {
  if (!editing.value || saving.value) return
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(form.daily_time)) { formError.value = '请选择有效的每日执行时刻'; return }
  saving.value = true
  formError.value = ''
  try {
    await updateJob(editing.value.code, { ...form })
    unsaved.markSaved()
    dialog.value = false
    ElMessage.success('每日计划已保存')
    await load()
  } catch (e) { formError.value = errorMessage(e, '保存失败，请重试') }
  finally { saving.value = false }
}
const historyJob = ref<ScheduledJob | null>(null)
const drawer = ref(false)
const records = ref<ScheduledRun[]>([])
const historyLoading = ref(false)
const historyError = ref('')
const page = ref(1)
const total = ref(0)
let historySeq = 0
async function loadHistory(quiet = false) {
  if (!historyJob.value) return
  const seq = ++historySeq
  historyLoading.value = !quiet
  try {
    const data = await listRuns(historyJob.value.code, page.value)
    if (seq !== historySeq || disposed) return
    records.value = data.items; total.value = data.total; historyError.value = ''
  } catch (e) { if (seq === historySeq) historyError.value = errorMessage(e, '执行记录加载失败') }
  finally { if (seq === historySeq) historyLoading.value = false }
}
function showHistory(job: ScheduledJob) {
  historyJob.value = job; page.value = 1; records.value = []; total.value = 0; drawer.value = true
  void loadHistory()
}
function duration(row: ScheduledRun) {
  if (!row.started_at || !row.finished_at) return '—'
  const seconds = Math.max(0, Math.round((Date.parse(row.finished_at) - Date.parse(row.started_at)) / 1000))
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}
let timer: ReturnType<typeof setTimeout> | undefined
async function poll() {
  if (!document.hidden) {
    await load(true)
    if (drawer.value && !historyLoading.value) await loadHistory(true)
  }
  if (!disposed) timer = setTimeout(() => { void poll() }, 5000)
}
onMounted(async () => { await load(); if (!disposed) timer = setTimeout(() => { void poll() }, 5000) })
onBeforeUnmount(() => { disposed = true; historySeq++; clearTimeout(timer) })
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
            <el-tag
              v-if="col.prop === 'enabled'"
              :type="row.enabled ? 'success' : 'info'"
              size="small"
            >
              {{ row.enabled ? '已启用' : '已停用' }}
            </el-tag>
            <el-tag
              v-else-if="col.prop === 'status'"
              :type="statusType(row.last_run?.status)"
              size="small"
            >
              {{ row.last_run ? statusText[row.last_run.status as ScheduledRun['status']] : '尚未执行' }}
            </el-tag>
            <span v-else>{{ cell(row, col.prop) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="250"
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
              设置计划
            </el-button>
            <el-button
              link
              type="primary"
              @click="showHistory(row)"
            >
              执行记录
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </ListPage>
    <p class="scheduler-note">
      “数据更新至”是源数据的入库时间，与任务结束时间不同。失败后最多重试 2 次，分别等待 1 分钟、5 分钟；同一任务不会重复执行。
    </p>
    <el-dialog
      v-model="dialog"
      :title="`设置计划 · ${editing?.name ?? ''}`"
      width="480px"
      :before-close="unsaved.beforeClose"
      :close-on-click-modal="false"
    >
      <el-alert
        v-if="formError"
        :title="formError"
        type="error"
        :closable="false"
        show-icon
      />
      <el-form
        label-position="top"
        :disabled="saving"
        @submit.prevent="save"
      >
        <el-form-item label="每日自动执行">
          <el-switch
            v-model="form.enabled"
            active-text="启用"
            inactive-text="停用"
          />
        </el-form-item>
        <el-form-item label="执行时刻（北京时间）">
          <el-time-select
            v-model="form.daily_time"
            start="00:00"
            step="00:10"
            end="23:50"
            :clearable="false"
            placeholder="选择执行时刻"
          />
        </el-form-item>
        <p class="scheduler-note">
          停用会取消排队和等待重试的任务，正在执行的批次会继续完成。停用期间仍可手动执行；重新启用后从下次计划时间开始。
        </p>
      </el-form>
      <template #footer>
        <el-button
          :disabled="saving"
          @click="unsaved.close"
        >
          取消
        </el-button><el-button
          type="primary"
          :loading="saving"
          @click="save"
        >
          保存计划
        </el-button>
      </template>
    </el-dialog>
    <el-drawer
      v-model="drawer"
      :title="`${historyJob?.name ?? ''} · 执行记录`"
      size="min(1120px, 96vw)"
    >
      <div class="history-toolbar">
        <span>共 {{ total }} 次执行 · 时间均为北京时间</span><el-button
          :loading="historyLoading"
          :icon="Refresh"
          @click="loadHistory()"
        >
          刷新记录
        </el-button>
      </div>
      <el-alert
        v-if="historyError"
        :title="historyError"
        type="error"
        :closable="false"
        show-icon
      />
      <ScrollPort class="history-table">
        <el-table
          v-loading="historyLoading"
          :data="records"
          row-key="id"
          :empty-text="historyLoading ? '正在加载执行记录…' : '暂无执行记录，计划触发或手动执行后会在这里显示。'"
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
                <template v-if="row.result">
                  <p>处理日期：{{ row.result.date_from || '—' }} 至 {{ row.result.date_to || '—' }}</p>
                  <p>数据更新至：{{ formatTime(row.result.watermark) }}</p>
                  <p v-if="row.result.days_synced !== undefined">
                    已处理 {{ row.result.days_synced }} 个采集日 · 网站快照 {{ row.result.site_rows ?? '—' }} 条
                  </p>
                  <p v-if="row.result.task_rows !== undefined">
                    任务基线 {{ row.result.task_rows }} 条 · 日统计 {{ row.result.stat_rows }} 条 · 健康快照 {{ row.result.health_rows }} 条
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
                {{ statusText[row.status as ScheduledRun['status']] }}
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
        </el-table>
      </ScrollPort>
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="prev, pager, next"
        @current-change="loadHistory()"
      />
    </el-drawer>
  </div>
</template>

<style scoped>
.scheduler-strip, .scheduler-strip > div, .history-toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.scheduler-strip { padding: 14px 16px; border: 1px solid var(--zt-border); background: var(--zt-panel); border-radius: var(--zt-radius); color: var(--zt-ink-500); font-size: 13px; }
.scheduler-note { color: var(--zt-ink-500); font-size: 13px; line-height: 1.8; margin: 16px 0; }
.scheduler-page :deep(.list-page) { min-height: 0; max-height: none; }
.scheduler-page :deep(.list-page__results) { flex: none; min-height: 180px; }
.history-toolbar { margin-bottom: 16px; color: var(--zt-ink-500); font-size: 13px; }
.history-table { height: min(66vh, 650px); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); margin: 16px 0; }
.run-detail { padding: 8px 24px; color: var(--zt-ink-700); font-size: 13px; overflow-wrap: anywhere; }
.run-detail p { line-height: 1.7; }
</style>
