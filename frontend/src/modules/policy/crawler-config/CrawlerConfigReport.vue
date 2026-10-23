<script setup lang="ts">
import { ArrowLeft, ArrowRight, CircleCheck, Clock, Refresh, TrendCharts, Warning } from '@element-plus/icons-vue'
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
import ConfigProvinces from './ConfigProvinces.vue'
import { coverageOption, deltaText, headline, rangeText, syncFailure, syncRunning, weekTitle, weeklyOption } from './report'

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
const ring = computed(() => (report.value ? coverageOption(report.value.totals, palette) : {}))
const trend = computed(() => weeklyOption(report.value?.trend ?? [], palette))
const isCurrentWeek = computed(() => !week.value || week.value === mondayOf(new Date()))
const sentences = computed(() => (report.value ? headline(report.value, isCurrentWeek.value) : []))
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
        <el-button
          :disabled="isCurrentWeek"
          @click="pickWeek(null)"
        >
          回到本周
        </el-button>
        <span
          v-if="report"
          class="config__range"
        >{{ rangeText(report.week_from, report.week_to) }}</span>
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
          hint="分省汇总、分省每周配置、本周新增明细、每周趋势、异常清单五个工作表。"
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
      <p
        class="config__headline"
        aria-live="polite"
      >
        <span
          v-for="(sentence, index) in sentences"
          :key="index"
        ><span
          v-for="(part, partIndex) in sentence"
          :key="partIndex"
          :class="[part.strong && 'is-strong', part.tone && `is-${part.tone}`]"
        >{{ part.text }}</span>{{ index < sentences.length - 1 ? '；' : '。' }}</span>
      </p>
      <section
        class="overview"
        aria-label="配置总览"
      >
        <div class="overview__ring">
          <div class="overview__chart">
            <BaseChart
              :option="ring"
              :label="`覆盖率 ${report.totals.coverage}%：已爬 ${report.totals.online} 个，未爬 ${report.totals.pending} 个，异常 ${report.totals.abnormal} 个`"
              height="168px"
            />
            <div
              class="overview__center"
              aria-hidden="true"
            >
              <strong>{{ report.totals.coverage }}<small>%</small></strong>
              <span>覆盖率</span>
            </div>
          </div>
          <p class="overview__caption">
            已配置 <b>{{ report.totals.online.toLocaleString() }}</b> / {{ report.totals.total.toLocaleString() }} 个栏目
          </p>
        </div>
        <ul class="overview__stats">
          <li class="stat stat--online">
            <span class="stat__icon"><el-icon><CircleCheck /></el-icon></span>
            <span class="stat__label">已配置栏目</span>
            <strong class="stat__value">{{ report.totals.online.toLocaleString() }}</strong>
            <span class="stat__foot">爬虫状态为已爬</span>
          </li>
          <li class="stat stat--new">
            <span class="stat__icon"><el-icon><TrendCharts /></el-icon></span>
            <span class="stat__label">{{ weekName }}新配置</span>
            <strong class="stat__value">{{ report.counted ? report.totals.new.toLocaleString() : '—' }}</strong>
            <span
              class="stat__foot"
              :class="delta && `is-${delta.tone}`"
            >{{ delta?.text ?? (report.counted ? '上周不在统计范围' : `${report.report_start} 那周开始统计`) }}</span>
          </li>
          <li class="stat stat--pending">
            <span class="stat__icon"><el-icon><Clock /></el-icon></span>
            <span class="stat__label">未配置栏目</span>
            <strong class="stat__value">{{ report.totals.pending.toLocaleString() }}</strong>
            <span class="stat__foot">信源表里还没爬的</span>
          </li>
          <li class="stat stat--abnormal">
            <span class="stat__icon"><el-icon><Warning /></el-icon></span>
            <span class="stat__label">异常栏目</span>
            <strong class="stat__value">{{ report.totals.abnormal.toLocaleString() }}</strong>
            <router-link
              v-if="abnormalLink && report.totals.abnormal"
              :to="abnormalLink"
              class="stat__foot stat__link"
            >
              去信源管理核对
            </router-link>
            <span
              v-else
              class="stat__foot"
            >需要业务核对</span>
          </li>
        </ul>
      </section>

      <section class="trend">
        <header class="trend__head">
          <el-icon aria-hidden="true">
            <TrendCharts />
          </el-icon>
          <div>
            <h2>每周配置进度</h2>
            <p>爬虫同事每周新配置上线的栏目数，鼠标移到柱子上看当周累计</p>
          </div>
        </header>
        <div
          v-if="!report.trend.length"
          class="trend__empty"
        >
          <el-icon aria-hidden="true">
            <TrendCharts />
          </el-icon>
          <p>{{ report.report_start }} 那周开始按周统计，每过一周这里多一根柱子，能看到每周配置了多少栏目。</p>
        </div>
        <BaseChart
          v-else
          :option="trend"
          :label="`每周新增上线栏目：${report.trend.map(item => `${item.week_from} 起 ${item.new} 个`).join('，')}`"
          height="280px"
        />
      </section>

      <ConfigProvinces
        :report="report"
        :current="isCurrentWeek"
      />
      <ConfigNewSites :report="report" />
    </template>
  </div>
</template>

<style scoped>
.config { display: flex; flex-direction: column; gap: 14px; }
.config__sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.config__bar, .overview, .trend { border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); }
.config__bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px 12px; padding: 12px 16px; }
.config__week, .config__actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.config__week .el-button + .el-button, .config__actions .el-button + .el-button { margin-left: 0; }
.config__picker { width: 168px; }
.config__range { margin-left: 4px; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; }
.config__headline {
  margin: 0; padding: 14px 18px; border-left: 3px solid var(--zt-blue-600); border-radius: var(--zt-radius);
  background: var(--el-color-primary-light-9); color: var(--zt-ink-700); font-size: 15px; line-height: 1.8;
}
.config__headline .is-strong { margin: 0 2px; color: var(--zt-ink-900); font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }
.config__headline .is-good { color: var(--el-color-success); }
.config__headline .is-bad { color: var(--el-color-danger); }
.config__sync { display: flex; align-items: center; gap: 6px; margin: -4px 0 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.6; }

.overview { display: grid; grid-template-columns: 260px minmax(0, 1fr); }
.overview__ring { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 16px; border-right: 1px solid var(--zt-border); }
.overview__chart { position: relative; width: 168px; }
.overview__center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
.overview__center strong { color: var(--zt-ink-900); font-size: 32px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }
.overview__center small { font-size: 16px; font-weight: 600; margin-left: 1px; }
.overview__center span { margin-top: 6px; color: var(--zt-ink-500); font-size: 12px; }
.overview__caption { margin: 0; color: var(--zt-ink-500); font-size: 13px; font-variant-numeric: tabular-nums; }
.overview__caption b { color: var(--zt-blue-600); font-size: 15px; }
.overview__stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 0; padding: 0; list-style: none; }
.stat {
  display: grid; grid-template-columns: 40px minmax(0, 1fr); grid-template-rows: auto auto auto; column-gap: 12px; row-gap: 4px;
  align-content: center; padding: 20px; --tone: var(--zt-blue-600);
}
.stat + .stat { border-left: 1px solid var(--zt-border); }
.stat--new { --tone: var(--chart-normal); }
.stat--pending { --tone: var(--zt-ink-500); }
.stat--abnormal { --tone: var(--chart-stale); }
.stat__icon {
  grid-row: 1 / span 3; align-self: start; display: grid; place-items: center; width: 40px; height: 40px;
  border-radius: 10px; font-size: 20px; color: var(--tone); background: color-mix(in srgb, var(--tone) 12%, transparent);
}
.stat__label { color: var(--zt-ink-700); font-size: 13px; }
.stat__value { color: var(--zt-ink-900); font-size: 30px; font-weight: 600; line-height: 1.15; font-variant-numeric: tabular-nums; }
.stat--online .stat__value, .stat--new .stat__value, .stat--abnormal .stat__value { color: var(--tone); }
.stat__foot { color: var(--zt-ink-500); font-size: 12px; font-variant-numeric: tabular-nums; }
.stat__foot.is-good { color: var(--el-color-success); }
.stat__foot.is-bad { color: var(--el-color-danger); }
.stat__link { color: var(--zt-blue-600); text-decoration: none; }
.stat__link:hover { text-decoration: underline; }

.trend { padding: 16px 20px 12px; min-width: 0; }
.trend__head { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; }
.trend__head > .el-icon { margin-top: 2px; font-size: 18px; color: var(--chart-normal); }
.trend__head h2 { margin: 0; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
.trend__head p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; }
.trend__empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 28px 16px 32px; color: var(--zt-ink-500); text-align: center; }
.trend__empty .el-icon { font-size: 28px; opacity: 0.5; }
.trend__empty p { margin: 0; font-size: 13px; }

@media (max-width: 1280px) {
  .overview__stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stat:nth-child(3) { border-left: 0; }
  .stat:nth-child(n + 3) { border-top: 1px solid var(--zt-border); }
}
@media (max-width: 760px) {
  .overview { grid-template-columns: minmax(0, 1fr); }
  .overview__ring { border-right: 0; border-bottom: 1px solid var(--zt-border); }
}
@media (prefers-reduced-motion: reduce) {
  .stat__link { transition: none; }
}
</style>
