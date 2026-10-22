<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { listJobs, triggerJob, updateJob, type ScheduledJob, type SchedulerOverview } from '@/api/scheduler'
import { errorMessage } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import { useUnsavedForm } from '@/composables/useUnsavedForm'
import ListPage from '@/components/ListPage.vue'
import ColumnPicker from '@/components/ColumnPicker.vue'
import type { DataColumn } from '@/components/dataColumns'
import AiTaggingPanel from './AiTaggingPanel.vue'
import SchedulerHistoryDrawer from './SchedulerHistoryDrawer.vue'
import { STATUS_TEXT, statusType, type RunStatus } from './runStatus'
import { useSchedulerHistory } from './useSchedulerHistory'

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
  const [message, title] = job.code === 'policy_ai'
    ? ['按下方设置从读取进度往后读一批源政策，用上线模板判断政策类型并写入基础标签，会产生模型费用（按每日上限封顶）。', '立即执行一批 AI 打标？']
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
              {{ row.last_run ? STATUS_TEXT[row.last_run.status as RunStatus] : '尚未执行' }}
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
              @click="history.open(row)"
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
    <AiTaggingPanel
      v-if="overview?.items.some(item => item.code === 'policy_ai')"
      :can-manage="canManage"
    />
    <SchedulerHistoryDrawer :history="history" />
  </div>
</template>

<style scoped>
.scheduler-strip, .scheduler-strip > div { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.scheduler-strip { padding: 14px 16px; border: 1px solid var(--zt-border); background: var(--zt-panel); border-radius: var(--zt-radius); color: var(--zt-ink-500); font-size: 13px; }
.scheduler-note { color: var(--zt-ink-500); font-size: 13px; line-height: 1.8; margin: 16px 0; }
.scheduler-page :deep(.list-page) { min-height: 0; max-height: none; }
.scheduler-page :deep(.list-page__results) { flex: none; min-height: 180px; }
</style>
