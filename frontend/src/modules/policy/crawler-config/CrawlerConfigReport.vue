<script setup lang="ts">
import { ArrowLeft, ArrowRight, Refresh } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  CRAWLER_CONFIG_BASE,
  getConfigSyncStatus,
  getCrawlerConfigReport,
  triggerConfigSync,
  type ConfigSyncStatus,
  type CrawlerConfigReport,
} from '@/api/crawlerConfig'
import { errorMessage } from '@/api/errors'
import BaseChart from '@/components/charts/BaseChart.vue'
import { chartPalette } from '@/components/charts/echarts'
import ExportButton from '@/components/ExportButton.vue'
import { useExcelExport } from '@/composables/useExcelExport'
import { useAuthStore } from '@/stores/auth'
import { configResultText } from '@/modules/system/scheduler/crawlerConfig'
import { formatTime } from '@/utils/time'
import ConfigReportTables from './ConfigReportTables.vue'
import { deltaText, syncFailure, syncRunning, weeklyOption } from './report'

const RESOURCE = 'policy.crawler_config'
const POLL_MS = 3000
const auth = useAuthStore()
const palette = chartPalette(getComputedStyle(document.documentElement))

const week = ref('')
const report = ref<CrawlerConfigReport | null>(null)
const status = ref<ConfigSyncStatus | null>(null)
const loading = ref(false)
const error = ref('')
const syncing = ref(false)
let sequence = 0
let pollTimer: ReturnType<typeof setTimeout> | undefined

const running = computed(() => syncRunning(status.value))
const failure = computed(() => syncFailure(status.value))
const delta = computed(() => (report.value ? deltaText(report.value.totals.new, report.value.previous_new) : null))
const chart = computed(() => weeklyOption(report.value?.trend ?? [], palette))
const isCurrentWeek = computed(() => !week.value || week.value === mondayOf(new Date()))
const lastSync = computed(() => {
  const sync = report.value?.last_sync
  return sync ? `规则表同步于 ${formatTime(sync.finished_at)}：${configResultText(sync)}` : '规则表还没有同步过'
})

const { exporting, onExport } = useExcelExport({
  path: `${CRAWLER_CONFIG_BASE}/report/export`,
  filename: () => `爬虫配置周报_${report.value?.week_from ?? ''}至${report.value?.week_to ?? ''}.xlsx`,
  filters: (): Record<string, string> => (week.value ? { week: week.value } : {}),
})

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function mondayOf(day: Date): string {
  const monday = new Date(day.getFullYear(), day.getMonth(), day.getDate() - ((day.getDay() + 6) % 7))
  return `${monday.getFullYear()}-${pad(monday.getMonth() + 1)}-${pad(monday.getDate())}`
}

function shiftWeek(weeks: number): void {
  const [year = 0, month = 1, day = 1] = (report.value?.week_from ?? mondayOf(new Date())).split('-').map(Number)
  pickWeek(mondayOf(new Date(year, month - 1, day + weeks * 7)))
}

function pickWeek(value: string | null): void {
  week.value = value ? mondayOf(new Date(`${value}T00:00:00`)) : ''
  void load()
}

async function load(): Promise<void> {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const data = await getCrawlerConfigReport(week.value || undefined)
    if (current === sequence) report.value = data
  } catch (cause) {
    if (current === sequence) error.value = errorMessage(cause, '暂时无法获取周报，请稍后重试。')
  } finally {
    if (current === sequence) loading.value = false
  }
}

/** 同步在排队或执行时每 3 秒看一次，结束后刷新周报。 */
async function pollStatus(): Promise<void> {
  clearTimeout(pollTimer)
  const wasRunning = running.value
  try {
    status.value = await getConfigSyncStatus()
  } catch {
    // 状态取不到不影响看周报，下一轮再试。
  }
  if (running.value) {
    pollTimer = setTimeout(() => void pollStatus(), POLL_MS)
  } else if (wasRunning) {
    await load()
    const result = status.value?.last_run
    if (result?.status === 'success') ElMessage.success(`同步完成，${configResultText(result.result)}`)
  }
}

async function syncNow(): Promise<void> {
  syncing.value = true
  try {
    await triggerConfigSync()
    ElMessage.info('已开始同步规则表，完成后自动刷新')
    status.value = { active_run: { status: 'queued' } as ConfigSyncStatus['active_run'], last_run: status.value?.last_run ?? null }
    pollTimer = setTimeout(() => void pollStatus(), POLL_MS)
  } catch (cause) {
    ElMessage.error(errorMessage(cause, '同步没有发起，请重试'))
  } finally {
    syncing.value = false
  }
}

onMounted(() => {
  void load()
  void pollStatus()
})
onBeforeUnmount(() => clearTimeout(pollTimer))
</script>

<template>
  <div
    v-loading="loading && !report"
    class="config-report"
  >
    <h1 class="config-report__sr-only">
      爬虫配置周报
    </h1>
    <section
      class="config-report__bar"
      aria-label="统计周"
    >
      <div class="config-report__week">
        <el-button
          :icon="ArrowLeft"
          aria-label="上一周"
          @click="shiftWeek(-1)"
        />
        <el-date-picker
          :model-value="report?.week_from ?? week"
          type="week"
          format="YYYY 第 ww 周"
          value-format="YYYY-MM-DD"
          :clearable="false"
          :disabled-date="(day: Date) => day.getTime() > Date.now()"
          aria-label="选择周"
          style="width: 150px"
          @update:model-value="pickWeek"
        />
        <el-button
          :icon="ArrowRight"
          aria-label="下一周"
          :disabled="isCurrentWeek"
          @click="shiftWeek(1)"
        />
        <el-button
          :disabled="isCurrentWeek"
          @click="pickWeek(null)"
        >
          本周
        </el-button>
        <span
          v-if="report"
          class="config-report__range"
        >{{ report.week_from }} 至 {{ report.week_to }}</span>
      </div>
      <div class="config-report__actions">
        <el-button
          v-if="auth.canFull(RESOURCE)"
          :icon="Refresh"
          :loading="syncing || running"
          @click="syncNow"
        >
          {{ running ? '正在同步规则表' : '立即同步' }}
        </el-button>
        <ExportButton
          :allowed="auth.canExport(RESOURCE)"
          :loading="exporting"
          :disabled="!report"
          hint="分省汇总、本周新增明细、每周趋势、异常清单四个工作表。"
          @click="onExport"
        />
      </div>
    </section>
    <p class="config-report__sync">
      {{ lastSync }}。每天 18:00 自动同步，爬虫同事更新规则表后也可以点「立即同步」。
    </p>
    <el-alert
      v-if="failure"
      :title="failure"
      type="error"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />
    <template v-if="report">
      <el-alert
        v-if="!report.counted"
        :title="`周报从 ${report.report_start} 那周开始统计新增。之前上线的 ${report.baseline.toLocaleString()} 个栏目算期初存量，不算进任何一周。`"
        type="info"
        :closable="false"
        show-icon
      />
      <section
        class="config-report__cards"
        aria-label="本周概况"
      >
        <div class="config-report__card config-report__card--main">
          <span>本周新增上线</span>
          <strong>{{ report.totals.new.toLocaleString() }}</strong>
          <em
            v-if="delta"
            :class="`delta-${delta.tone}`"
          >{{ delta.text }}</em>
          <em v-else>{{ report.counted ? '上周不在统计范围' : '本周不计新增' }}</em>
        </div>
        <div class="config-report__card">
          <span>栏目总数</span>
          <strong>{{ report.totals.total.toLocaleString() }}</strong>
          <em>信源表全部栏目</em>
        </div>
        <div class="config-report__card">
          <span>已爬</span>
          <strong>{{ report.totals.online.toLocaleString() }}</strong>
          <em>覆盖率 {{ report.totals.coverage }}%</em>
        </div>
        <div class="config-report__card">
          <span>未爬</span>
          <strong>{{ report.totals.pending.toLocaleString() }}</strong>
          <em>含未填爬虫状态</em>
        </div>
        <div class="config-report__card">
          <span>异常</span>
          <strong class="config-report__abnormal">{{ report.totals.abnormal.toLocaleString() }}</strong>
          <em>清单见下载的 Excel</em>
        </div>
      </section>
      <section class="config-report__panel">
        <header class="config-report__head">
          <h2>每周新增上线</h2>
          <p>按上线时间落在哪一周统计；累计含期初存量 {{ report.baseline.toLocaleString() }} 个</p>
        </header>
        <p
          v-if="!report.trend.length"
          class="config-report__empty"
        >
          从 {{ report.report_start }} 那周开始出趋势
        </p>
        <BaseChart
          v-else
          :option="chart"
          :label="`每周新增上线栏目：${report.trend.map(item => `${item.week_from} 起 ${item.new} 个`).join('，')}`"
          height="300px"
        />
      </section>
      <ConfigReportTables :report="report" />
    </template>
  </div>
</template>

<style scoped>
.config-report { display: flex; flex-direction: column; gap: 12px; }
.config-report__sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.config-report__bar, .config-report__panel, .config-report__cards {
  border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel);
}
.config-report__bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px 12px; padding: 12px 16px; }
.config-report__week, .config-report__actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.config-report__week .el-button + .el-button, .config-report__actions .el-button + .el-button { margin-left: 0; }
.config-report__range { color: var(--zt-ink-700); font-size: 13px; font-variant-numeric: tabular-nums; }
.config-report__sync { margin: 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
.config-report__cards { display: grid; grid-template-columns: minmax(0, 1.4fr) repeat(4, minmax(0, 1fr)); }
.config-report__card { display: flex; flex-direction: column; gap: 4px; padding: 14px 18px; min-width: 0; }
.config-report__card + .config-report__card { border-left: 1px solid var(--zt-border); }
.config-report__card span { color: var(--zt-ink-500); font-size: 13px; }
.config-report__card strong { color: var(--zt-ink-900); font-size: 24px; font-weight: 600; line-height: 1.2; font-variant-numeric: tabular-nums; }
.config-report__card--main strong { font-size: 32px; color: var(--zt-blue-600); }
.config-report__card em { color: var(--zt-ink-500); font-size: 12px; font-style: normal; font-variant-numeric: tabular-nums; }
.config-report__card .config-report__abnormal { color: var(--chart-stale); }
.delta-good { color: var(--el-color-success) !important; }
.delta-bad { color: var(--el-color-danger) !important; }
.config-report__panel { padding: 14px 18px; min-width: 0; }
.config-report__head { margin-bottom: 8px; }
.config-report__head h2 { margin: 0; color: var(--zt-ink-900); font-size: 14px; font-weight: 600; }
.config-report__head p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; }
.config-report__empty { margin: 0; padding: 40px 0; color: var(--zt-ink-500); font-size: 13px; text-align: center; }
@media (max-width: 900px) {
  .config-report__cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .config-report__card--main { grid-column: 1 / -1; }
  .config-report__card + .config-report__card { border-left: 0; border-top: 1px solid var(--zt-border); }
}
</style>
