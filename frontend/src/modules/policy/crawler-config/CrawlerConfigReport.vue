<script setup lang="ts">
import { ArrowLeft, ArrowRight, Clock, Refresh } from '@element-plus/icons-vue'
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
import { configResultText } from '@/modules/system/scheduler/crawlerConfig'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/time'
import ConfigNewSites from './ConfigNewSites.vue'
import ConfigOverview from './ConfigOverview.vue'
import ConfigProvinceTable from './ConfigProvinceTable.vue'
import { rangeText, syncFailure, syncRunning, trendWorthShowing, weekTitle, weeklyOption } from './report'

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
/** 分省表里点中的省份：明细只看这个省，换周后清掉。 */
const province = ref('')
let sequence = 0
let pollTimer: ReturnType<typeof setTimeout> | undefined

const running = computed(() => syncRunning(status.value))
const failure = computed(() => syncFailure(status.value))
const trend = computed(() => weeklyOption(report.value?.trend ?? [], palette))
const isCurrentWeek = computed(() => !week.value || week.value === mondayOf(new Date()))
const abnormalLink = computed(() => (auth.canRead('policy.sources') ? { path: '/policy/sources', query: { crawler_status: '异常' } } : null))
/** 领导只看数据更新时间；能同步的人再看规则表的对账细节（没填编码、信源表里没有的）。 */
const lastSync = computed(() => {
  const sync = report.value?.last_sync
  if (!sync) return '规则表还没有同步过'
  const time = `数据更新于 ${formatTime(sync.finished_at).slice(0, 16)}`
  return auth.canFull(RESOURCE) ? `${time}：${configResultText(sync)}` : time
})
const weekName = computed(() => (isCurrentWeek.value ? '本周' : weekTitle(report.value?.week_from ?? '')))

const { exporting, onExport } = useExcelExport({
  path: `${CRAWLER_CONFIG_BASE}/report/export`,
  filename: () => `爬虫配置统计_${report.value?.week_from ?? ''}至${report.value?.week_to ?? ''}.xlsx`,
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
  province.value = ''
  void load()
}

/** 点趋势图里的某一周，整页切到那一周。 */
function pickTrendWeek(params: { dataIndex: number }): void {
  const picked = report.value?.trend[params.dataIndex]
  if (picked) pickWeek(picked.week_from === mondayOf(new Date()) ? null : picked.week_from)
}

async function load(): Promise<void> {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const data = await getCrawlerConfigReport(week.value || undefined)
    if (current === sequence) report.value = data
  } catch (cause) {
    if (current === sequence) error.value = errorMessage(cause, '暂时无法获取统计，请稍后重试。')
  } finally {
    if (current === sequence) loading.value = false
  }
}

/** 同步在排队或执行时每 3 秒看一次，结束后刷新统计。 */
async function pollStatus(): Promise<void> {
  clearTimeout(pollTimer)
  const wasRunning = running.value
  try {
    status.value = await getConfigSyncStatus()
  } catch {
    // 状态取不到不影响看统计，下一轮再试。
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
    class="config"
  >
    <h1 class="config__sr-only">
      爬虫配置统计
    </h1>
    <section
      class="config__bar"
      aria-label="统计周"
    >
      <div class="config__week">
        <el-button
          :icon="ArrowLeft"
          aria-label="上一周"
          @click="shiftWeek(-1)"
        />
        <el-date-picker
          :model-value="report?.week_from ?? week"
          type="week"
          format="YYYY 年第 ww 周"
          value-format="YYYY-MM-DD"
          :clearable="false"
          :disabled-date="(day: Date) => day.getTime() > Date.now()"
          aria-label="选择周"
          class="config__picker"
          @update:model-value="pickWeek"
        />
        <el-button
          :icon="ArrowRight"
          aria-label="下一周"
          :disabled="isCurrentWeek"
          @click="shiftWeek(1)"
        />
        <span
          v-if="report"
          class="config__range"
        >{{ rangeText(report.week_from, report.week_to) }}</span>
        <el-button
          v-if="!isCurrentWeek"
          link
          type="primary"
          @click="pickWeek(null)"
        >
          回到本周
        </el-button>
      </div>
      <div class="config__actions">
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
          hint="第一张是所选这周各省配置网站数量，另有分省每周配置、分省累计、配置明细、每周趋势、异常清单。"
          @click="onExport"
        >
          下载报告
        </ExportButton>
      </div>
    </section>
    <p class="config__sync">
      <el-icon aria-hidden="true">
        <Clock />
      </el-icon>
      {{ lastSync }}。每天 18:00 按爬虫同事的规则表自动更新。
    </p>
    <el-alert
      v-if="failure || error"
      :title="failure || error"
      type="error"
      :closable="false"
      show-icon
    />

    <template v-if="report">
      <ConfigOverview
        :report="report"
        :week-name="weekName"
        :abnormal-link="abnormalLink"
      />
      <section
        v-if="trendWorthShowing(report.trend)"
        class="trend"
      >
        <header>
          <h2>每周配置数量</h2>
          <p>近 12 周，深色是{{ weekName }}；点柱子查看那一周</p>
        </header>
        <BaseChart
          :option="trend"
          :label="`近 12 周每周配置网站数量：${report.trend.map(item => `${item.week_from} 起 ${item.new} 个`).join('，')}`"
          height="220px"
          @select="pickTrendWeek"
        />
      </section>
      <ConfigProvinceTable
        :report="report"
        :week-name="weekName"
        :selected="province"
        @select="province = $event"
      />
      <ConfigNewSites
        :report="report"
        :week-name="weekName"
        :province="province"
        @clear="province = ''"
      />
    </template>
  </div>
</template>

<style scoped>
.config { display: flex; flex-direction: column; gap: 14px; }
.config__sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.config__bar, .trend { border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); }
.config__bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px 12px; padding: 12px 16px; }
.config__week, .config__actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.config__week .el-button + .el-button, .config__actions .el-button + .el-button { margin-left: 0; }
.config__picker { width: 168px; }
.config__range { margin: 0 4px; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; }
.config__sync { display: flex; align-items: center; gap: 6px; margin: -4px 0 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }
.trend { padding: 16px 20px 8px; min-width: 0; }
.trend h2 { margin: 0; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
.trend p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; }
</style>
