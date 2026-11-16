<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { errorMessage } from '@/api/errors'
import { getTenderStatistics, getTenderTotals, type TenderStatistics, type TenderTotals } from '@/api/tender'
import BaseChart from '@/components/charts/BaseChart.vue'
import { useChartPalette } from '@/components/charts/echarts'
import TenderDailyTable from './TenderDailyTable.vue'
import TenderKpiGrid from './TenderKpiGrid.vue'
import TenderProvincePanel from './TenderProvincePanel.vue'
import TenderStatsSkeleton from './TenderStatsSkeleton.vue'
import { compactCount, recentRange, statisticsChart, structureDonutOption } from './statistics'

const PRESETS = [
  { days: 7, label: '近 7 天' }, { days: 14, label: '近 14 天' }, { days: 30, label: '近 30 天' },
] as const

const preset = ref<number | null>(7)
const range = ref<[string, string]>(recentRange(new Date(), 7))
const intakeMode = ref<'bar' | 'line'>('bar')
const report = ref<TenderStatistics | null>(null)
const totals = ref<TenderTotals | null>(null)
const error = ref('')
const totalError = ref('')
const loading = ref(false)
const totalsLoading = ref(false)
let totalTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false
onBeforeUnmount(() => { disposed = true; clearTimeout(totalTimer) })

const palette = useChartPalette()
let sequence = 0

const intakeChart = computed(() => statisticsChart(report.value?.daily ?? [], palette.value, 'intake', intakeMode.value))
const workChart = computed(() => statisticsChart(report.value?.daily ?? [], palette.value, 'work', 'bar'))
const donutOption = computed(() =>
  structureDonutOption(
    totals.value?.purchaser ?? 0,
    totals.value?.winbid ?? 0,
    totals.value?.purchaser_passed ?? 0,
    totals.value?.winbid_passed ?? 0,
    palette.value,
  ),
)

const workload = computed(() => report.value?.daily.reduce((sum, row) => sum + row.tagged, 0) ?? 0)
const rangeTotals = computed(() => {
  const daily = report.value?.daily ?? []
  const purchaser = daily.reduce((sum, row) => sum + row.purchaser, 0)
  const winbid = daily.reduce((sum, row) => sum + row.winbid, 0)
  const total = purchaser + winbid
  const days = daily.length || 1
  return { purchaser, winbid, total, days: daily.length, dailyAvg: Math.round(total / days) }
})

const sharePct = (part?: number, whole?: number) => (!part || !whole ? '0.0%' : `${((part * 100) / whole).toFixed(1)}%`)
const count = (value?: number) => (value === undefined ? '—' : value.toLocaleString('zh-CN'))
const formatTime = (iso?: string) => (iso ? iso.replace('T', ' ').slice(0, 19) : '—')

const topProvince = computed(() => report.value?.provinces?.[0] ?? null)

async function load() {
  const current = ++sequence
  error.value = ''
  if (!range.value?.[0] || !range.value[1]) {
    error.value = '请选择统计日期范围'
    return
  }
  loading.value = true
  try {
    const result = await getTenderStatistics(...range.value)
    if (current === sequence) report.value = result
  } catch (cause) {
    if (current === sequence) error.value = errorMessage(cause, '统计加载失败')
  } finally {
    if (current === sequence) loading.value = false
  }
}

async function loadTotals() {
  clearTimeout(totalTimer)
  totalsLoading.value = true
  totalError.value = ''
  try {
    const result = await getTenderTotals()
    if (disposed) return
    if (result.data) totals.value = result.data
    if (result.state === 'pending') {
      totalTimer = setTimeout(() => { void loadTotals() }, 3000)
      return
    }
    totalsLoading.value = false
    if (result.state === 'error') totalError.value = result.message
    else totals.value = result.data
  } catch (cause) {
    totalError.value = errorMessage(cause, '总量加载失败')
    totalsLoading.value = false
  }
}

function pickPreset(days: number) { preset.value = days; range.value = recentRange(new Date(), days); void load() }
function onRangeChange() { preset.value = null }

onMounted(() => { void load(); void loadTotals() })
</script>

<template>
  <div class="tender-stats">
    <header class="stats-bar">
      <div class="stats-bar__title">
        <h1>招中标统计分析</h1>
        <span
          class="status-pill"
          :class="{ 'is-updating': totalsLoading }"
        >
          <span class="status-dot" />
          <template v-if="totalsLoading && !totals">后台统计中…</template>
          <template v-else-if="totalsLoading">正在后台更新 · 上次 {{ formatTime(totals?.as_of).slice(11) }}</template>
          <template v-else-if="totals">后台每 30 秒自动保鲜 · 更新于 {{ formatTime(totals.as_of).slice(11) }}</template>
          <template v-else>等待数据源就绪</template>
        </span>
      </div>
      <form
        class="stats-bar__controls"
        @submit.prevent="load"
      >
        <el-radio-group
          :model-value="preset"
          size="small"
          aria-label="快捷时间范围"
          @change="(value: string | number | boolean | undefined) => pickPreset(Number(value))"
        >
          <el-radio-button
            v-for="item in PRESETS"
            :key="item.days"
            :value="item.days"
          >
            {{ item.label }}
          </el-radio-button>
        </el-radio-group>
        <el-date-picker
          v-model="range"
          type="daterange"
          size="small"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          :clearable="false"
          unlink-panels
          style="width: 240px"
          @change="onRangeChange"
        />
        <el-button
          type="primary"
          size="small"
          native-type="submit"
          :loading="loading"
        >
          查询
        </el-button>
        <el-button
          size="small"
          :icon="Refresh"
          :loading="totalsLoading"
          @click="loadTotals"
        >
          刷新总量
        </el-button>
      </form>
    </header>

    <el-alert
      v-if="totalError"
      :title="totalError"
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
    >
      <el-button
        size="small"
        @click="load"
      >
        重试
      </el-button>
    </el-alert>

    <p
      v-if="totals || report"
      class="headline"
      aria-live="polite"
    >
      <template v-if="totals">
        全库累计接入原始数据 <strong class="hl-strong">{{ compactCount(totals.total) }}</strong> 条（招标占 <strong>{{ sharePct(totals.purchaser, totals.total) }}</strong>，中标占 <strong>{{ sharePct(totals.winbid, totals.total) }}</strong>）；
      </template>
      <template v-if="report && !error">
        {{ report.date_from }} 至 {{ report.date_to }} 共采集入库 <strong class="hl-strong">{{ count(rangeTotals.total) }}</strong> 条（日均 <strong>{{ count(rangeTotals.dailyAvg) }}</strong> 条），
        <template v-if="topProvince">
          <strong>{{ topProvince.province || '未填写省份' }}</strong> 体量居首（{{ count(topProvince.purchaser + topProvince.winbid) }} 条），
        </template>
        已完成人工信息化及基础字段补充 <strong class="hl-good">{{ count(workload) }}</strong> 条。
      </template>
    </p>
    <p
      v-else-if="totalsLoading"
      class="headline"
      role="status"
      aria-label="摘要数据统计中"
    >
      <span
        class="skeleton-shimmer"
        style="width: 55%; height: 14px; border-radius: 4px; display: inline-block;"
      />
    </p>

    <TenderKpiGrid
      :totals="totals"
      :totals-loading="totalsLoading"
      :has-report="Boolean(report)"
      :range-totals="rangeTotals"
      :workload="workload"
    />

    <template v-if="report && !error">
      <div class="grid-row grid-row--top">
        <section
          class="panel panel--main"
          :class="{ 'is-refreshing': loading }"
        >
          <header class="panel-head">
            <div>
              <h2>每日数据接入趋势</h2>
              <p class="panel-note">
                按采集日期统计（单次最多 31 天）；区间招标 {{ count(rangeTotals.purchaser) }} 条、中标 {{ count(rangeTotals.winbid) }} 条
              </p>
            </div>
            <el-radio-group
              v-model="intakeMode"
              size="small"
              aria-label="接入趋势图类型"
            >
              <el-radio-button value="bar">
                分组柱状
              </el-radio-button>
              <el-radio-button value="line">
                平滑趋势
              </el-radio-button>
            </el-radio-group>
          </header>
          <BaseChart
            :option="intakeChart"
            label="招标与中标每日接入数量"
            height="260px"
          />
        </section>

        <section class="panel panel--side">
          <header class="panel-head">
            <div>
              <h2>全库结构占比</h2>
              <p class="panel-note">
                原始库口径，不含重复统计
              </p>
            </div>
          </header>
          <div class="donut-wrap">
            <BaseChart
              :option="donutOption"
              label="招标与中标全库占比结构"
              height="185px"
            />
            <div
              class="donut-center"
              aria-hidden="true"
            >
              <strong>{{ totals ? compactCount(totals.total) : '—' }}</strong>
              <span>累计总规模</span>
            </div>
          </div>
          <div class="donut-legend">
            <div class="legend-card">
              <div class="lc-head">
                <span class="dot-label"><span class="dot dot--primary" />招标公告原始库</span>
                <span class="tabular"><strong>{{ count(totals?.purchaser) }}</strong> ({{ sharePct(totals?.purchaser, totals?.total) }})</span>
              </div>
              <div class="lc-split">
                <span class="pill-item pill-p-pass">
                  <span class="pill-label"><span class="pill-dot pill-dot--p" />审核通过</span>
                  <span class="tabular"><strong>{{ count(totals?.purchaser_passed) }}</strong> ({{ sharePct(totals?.purchaser_passed, totals?.purchaser) }})</span>
                </span>
                <span class="pill-item pill-p-unpass">
                  <span class="pill-label"><span class="pill-dot pill-dot--p-unpass" />待审未通过</span>
                  <span class="tabular"><strong>{{ count(totals ? totals.purchaser - (totals.purchaser_passed ?? 0) : undefined) }}</strong> ({{ sharePct(totals ? totals.purchaser - (totals.purchaser_passed ?? 0) : 0, totals?.purchaser) }})</span>
                </span>
              </div>
            </div>
            <div class="legend-card">
              <div class="lc-head">
                <span class="dot-label"><span class="dot dot--success" />中标公告原始库</span>
                <span class="tabular"><strong>{{ count(totals?.winbid) }}</strong> ({{ sharePct(totals?.winbid, totals?.total) }})</span>
              </div>
              <div class="lc-split">
                <span class="pill-item pill-w-pass">
                  <span class="pill-label"><span class="pill-dot pill-dot--w" />审核通过</span>
                  <span class="tabular"><strong>{{ count(totals?.winbid_passed) }}</strong> ({{ sharePct(totals?.winbid_passed, totals?.winbid) }})</span>
                </span>
                <span class="pill-item pill-w-unpass">
                  <span class="pill-label"><span class="pill-dot pill-dot--w-unpass" />待审未通过</span>
                  <span class="tabular"><strong>{{ count(totals ? totals.winbid - (totals.winbid_passed ?? 0) : undefined) }}</strong> ({{ sharePct(totals ? totals.winbid - (totals.winbid_passed ?? 0) : 0, totals?.winbid) }})</span>
                </span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="grid-row grid-row--mid">
        <section
          class="panel"
          :class="{ 'is-refreshing': loading }"
        >
          <header class="panel-head">
            <div>
              <h2>每日人工审核处理趋势</h2>
              <p class="panel-note">
                信息化标签与基础字段补充按已处理状态计数，两项工序不相加计算数据条数
              </p>
            </div>
          </header>
          <div class="work-chips">
            <div><span>信息化标签</span><strong class="tabular">{{ count(workload) }}</strong></div>
            <div><span>基础字段补充</span><strong class="tabular">{{ count(workload) }}</strong></div>
            <div><span>场景补充（暂未开展）</span><strong class="tabular">0</strong></div>
          </div>
          <BaseChart
            :option="workChart"
            label="每日信息化标签、基础字段补充与场景处理量"
            height="210px"
          />
        </section>

        <TenderDailyTable
          :daily="report.daily"
          :loading="loading"
          :as-of="report.as_of"
        />
      </div>

      <TenderProvincePanel :provinces="report.provinces" />
    </template>

    <template v-else-if="loading">
      <TenderStatsSkeleton />
    </template>
  </div>
</template>

<style scoped src="./tender-statistics.css"></style>
