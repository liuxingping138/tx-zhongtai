<script setup lang="ts">
import { ArrowDown, ArrowUp, Refresh } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'

import { getCrawlerOverview, type CrawlerOverviewData, type SiteStatus } from '@/api/crawlerMonitoring'
import { errorMessage } from '@/api/errors'
import { changeText, headline, weekDelta } from './charts'
import CrawlerHealthChart from './CrawlerHealthChart.vue'
import CrawlerProvinceChart from './CrawlerProvinceChart.vue'
import CrawlerTrendChart from './CrawlerTrendChart.vue'
import { compactCount } from './filters'

defineProps<{ selectedStatuses: SiteStatus[]; selectedProvinces: string[] }>()
const emit = defineEmits<{
  pickStatus: [status: SiteStatus]
  pickProvince: [rawNames: string[]]
  retry: []
}>()

const OVERVIEW_ERROR = '暂时无法获取采集概况，请稍后重试。'
const overview = ref<CrawlerOverviewData | null>(null)
const loading = ref(false)
const error = ref('')
const expanded = ref(true)
const trend = ref<InstanceType<typeof CrawlerTrendChart>>()
const sentences = computed(() => (overview.value ? headline(overview.value) : []))
let sequence = 0

const syncNotice = computed(() => {
  const sync = overview.value?.sync
  if (!sync) return ''
  if (sync.status === 'failed') return '最近一次同步失败，统计可能不是最新。请联系管理员检查同步任务。'
  if (sync.status === 'interrupted') return '最近一次同步意外中断，统计可能不完整。请重新执行同步。'
  if (sync.status === 'running') return '数据正在同步，完成后点「刷新统计」即可看到最新结果。'
  if (!sync.last_success_at) return '尚未完成首次同步。完成回填后，这里将显示采集概况。'
  if (sync.outdated) return '统计已超过 36 小时未更新，请检查同步任务。'
  return ''
})

const recentChange = computed(() => {
  const recent = overview.value?.recent
  return recent ? changeText(recent.rows, recent.previous_rows) : null
})

const statusCards = computed(() => {
  const data = overview.value
  if (!data) return []
  const { normal_days: normalDays, watch_days: watchDays } = data.thresholds
  const base = data.week_base
  const delta = (status: SiteStatus) => (base ? weekDelta(data.cards[status], base[status], status === 'normal') : null)
  return [
    { status: 'normal' as const, label: '正常', value: data.cards.normal, foot: `${normalDays} 天内有新数据入库`, delta: delta('normal') },
    { status: 'watch' as const, label: '关注', value: data.cards.watch, foot: `${normalDays + 1}–${watchDays} 天无新数据`, delta: delta('watch') },
    { status: 'stale' as const, label: '停更', value: data.cards.stale, foot: `超过 ${watchDays} 天无新数据`, delta: delta('stale') },
  ]
})

async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const result = await getCrawlerOverview()
    if (current === sequence) overview.value = result
  } catch (cause) {
    if (current !== sequence) return
    const message = errorMessage(cause, OVERVIEW_ERROR)
    error.value = message === '请求失败' ? OVERVIEW_ERROR : message
  } finally {
    if (current === sequence) loading.value = false
  }
}

async function reload() {
  await Promise.all([load(), trend.value?.load()])
}

defineExpose({ reload })
</script>

<template>
  <div class="overview-heading">
    <div class="overview-caption">
      <h2>采集概况</h2>
      <span
        v-if="overview?.sync.last_success_at"
        class="sync-time"
      >更新于 {{ overview.sync.last_success_at }}</span>
    </div>
    <div class="overview-actions">
      <el-button
        :icon="Refresh"
        text
        :loading="loading"
        @click="reload"
      >
        刷新统计
      </el-button>
      <el-button
        :icon="expanded ? ArrowUp : ArrowDown"
        text
        :aria-expanded="expanded"
        aria-controls="crawler-overview"
        @click="expanded = !expanded"
      >
        {{ expanded ? '收起概览' : '展开概览' }}
      </el-button>
    </div>
  </div>
  <el-alert
    v-if="syncNotice"
    :title="syncNotice"
    :type="['failed', 'interrupted'].includes(overview?.sync.status ?? '') ? 'error' : 'warning'"
    :closable="false"
    show-icon
    class="sync-notice"
  />
  <section
    v-show="expanded"
    id="crawler-overview"
    v-loading="loading && !overview"
    class="overview"
  >
    <div
      v-if="error"
      class="overview-error"
      role="alert"
    >
      {{ error }}
      <el-button
        link
        type="primary"
        @click="emit('retry')"
      >
        重试
      </el-button>
    </div>
    <template v-else-if="overview">
      <p
        class="headline"
        aria-live="polite"
      >
        <span
          v-for="(sentence, index) in sentences"
          :key="index"
          class="headline-sentence"
        ><span
          v-for="(part, partIndex) in sentence"
          :key="partIndex"
          :class="[part.strong && 'headline-strong', part.tone && `delta-${part.tone}`]"
        >{{ part.text }}</span>{{ index < sentences.length - 1 ? '；' : '。' }}</span>
      </p>
      <div class="cards">
        <div class="card">
          <span class="card-label">网站总数</span>
          <strong class="card-value">{{ overview.cards.sites.toLocaleString() }}</strong>
          <span class="card-foot">名称 + 省份 + 地市</span>
        </div>
        <button
          v-for="card in statusCards"
          :key="card.status"
          type="button"
          class="card card-status"
          :class="[`card-${card.status}`, { selected: selectedStatuses.includes(card.status) }]"
          :aria-pressed="selectedStatuses.includes(card.status)"
          :title="selectedStatuses.includes(card.status) ? '再次点击取消筛选' : `筛选${card.label}网站`"
          @click="emit('pickStatus', card.status)"
        >
          <span class="card-label"><span class="dot" />{{ card.label }}</span>
          <strong class="card-value">{{ card.value.toLocaleString() }}</strong>
          <span class="card-foot">{{ card.foot }}</span>
          <span
            v-if="card.delta"
            class="card-delta"
            :class="`delta-${card.delta.tone}`"
            :title="`与 ${overview.week_base?.date} 相比`"
          >{{ card.delta.text }}</span>
        </button>
        <div class="card">
          <span class="card-label">数据总量</span>
          <strong
            class="card-value"
            :title="`${overview.cards.total_rows.toLocaleString()} 条`"
          >{{ compactCount(overview.cards.total_rows) }}</strong>
          <span class="card-foot">不含已删除数据</span>
        </div>
        <div class="card">
          <span class="card-label">近 {{ overview.recent.days }} 天采集</span>
          <strong
            class="card-value"
            :title="`${overview.recent.rows.toLocaleString()} 条`"
          >{{ compactCount(overview.recent.rows) }}</strong>
          <span
            class="card-foot"
            :class="recentChange && `trend-${recentChange.trend}`"
            :title="`前 ${overview.recent.days} 天 ${overview.recent.previous_rows.toLocaleString()} 条`"
          >较前 {{ overview.recent.days }} 天 {{ recentChange?.text }}</span>
        </div>
      </div>
      <div class="chart-row">
        <CrawlerTrendChart ref="trend" />
        <CrawlerHealthChart
          :overview="overview"
          :selected="selectedStatuses"
          @pick="status => emit('pickStatus', status)"
        />
      </div>
      <CrawlerProvinceChart
        :provinces="overview.provinces"
        :selected="selectedProvinces"
        @pick="names => emit('pickProvince', names)"
      />
    </template>
  </section>
</template>

<style scoped>
.overview-heading, .overview-caption, .overview-actions { display: flex; align-items: center; gap: 12px; }
.overview-heading { justify-content: space-between; flex-wrap: wrap; margin-bottom: 10px; }
.overview-caption { flex-wrap: wrap; gap: 8px 14px; }
.overview-caption h2 { margin: 0; font-size: 14px; font-weight: 650; color: var(--zt-ink-900); }
.sync-time { color: var(--zt-ink-500); font-size: 12px; font-variant-numeric: tabular-nums; }
.overview-actions { gap: 2px; }
.overview-actions .el-button { margin: 0; }
.sync-notice { margin-bottom: 12px; }
.overview { display: flex; flex-direction: column; gap: var(--zt-space-3); margin-bottom: var(--zt-space-3); min-height: 110px; }
.overview-error { color: var(--zt-ink-700); font-size: 13px; }

.headline {
  margin: 0; padding: 10px 16px;
  background: var(--zt-panel); border: 1px solid var(--zt-border); border-left: 3px solid var(--zt-blue-600);
  border-radius: var(--zt-radius); box-shadow: var(--zt-shadow);
  font-size: 13.5px; line-height: 1.8; color: var(--zt-ink-700);
}
.headline-strong { font-size: 15px; font-weight: 650; color: var(--zt-ink-900); font-variant-numeric: tabular-nums; }

.cards { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: var(--zt-space-3); }
.card, .chart-panel {
  background: var(--zt-panel); border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius); box-shadow: var(--zt-shadow);
}
.card {
  display: flex; flex-direction: column; gap: 4px; min-height: 108px;
  padding: 14px 16px; font: inherit; text-align: left; color: inherit;
}
.card-status {
  cursor: pointer;
  transition: background-color 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}
.card-status:hover {
  border-color: var(--zt-border-strong);
  box-shadow: 0 4px 12px var(--zt-shadow-soft);
}
.card-status:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.card-status.selected {
  background: var(--el-color-primary-light-9);
  border-color: var(--zt-blue-600);
  box-shadow: inset 0 0 0 1px var(--zt-blue-600);
}
.card-label { display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 500; color: var(--zt-ink-500); }
.card-value { margin: 2px 0; font-size: 26px; font-weight: 650; letter-spacing: -0.02em; line-height: 1.15; color: var(--zt-ink-900); font-variant-numeric: tabular-nums; }
.card-foot { font-size: 12px; color: var(--zt-ink-500); }
.card-delta { font-size: 12px; font-weight: 500; font-variant-numeric: tabular-nums; }
.delta-good { color: var(--zt-success-text); }
.delta-bad { color: var(--zt-danger-text); }
.delta-flat { color: var(--zt-ink-500); }
.trend-up { color: var(--zt-success-text); }
.trend-down { color: var(--zt-danger-text); }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.card-normal .dot { background: var(--chart-normal); }
.card-watch .dot { background: var(--chart-watch); }
.card-stale .dot { background: var(--chart-stale); }
.card-stale .card-value { color: var(--chart-stale); }

.chart-row { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: var(--zt-space-3); }
.chart-panel { padding: 14px 18px; min-width: 0; }
.chart-panel :deep(.chart-head) {
  display: flex; justify-content: space-between; align-items: flex-start; gap: var(--zt-space-3);
  flex-wrap: wrap; margin-bottom: var(--zt-space-2);
}
.chart-panel :deep(h3) { margin: 0; font-size: 14px; font-weight: 650; color: var(--zt-ink-900); }
.chart-panel :deep(.chart-note) { margin: 3px 0 0; font-size: 12px; color: var(--zt-ink-500); }
.chart-panel :deep(.chart-error) { padding: var(--zt-space-6) 0; color: var(--zt-ink-700); font-size: 13px; }

@media (max-width: 1280px) {
  .cards { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .chart-row { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 767px) {
  .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
