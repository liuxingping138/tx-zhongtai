<script setup lang="ts">
import { computed } from 'vue'

import type { CrawlerOverviewData, SiteStatus } from '@/api/crawlerMonitoring'
import BaseChart from '@/components/charts/BaseChart.vue'
import { chartPalette } from '@/components/charts/echarts'
import { healthOption, healthSlices, percent, rateDelta } from './charts'

const props = defineProps<{ overview: CrawlerOverviewData; selected: SiteStatus[] }>()
const emit = defineEmits<{ pick: [status: SiteStatus] }>()

const palette = chartPalette(getComputedStyle(document.documentElement))
const slices = computed(() => healthSlices(props.overview.health, props.overview.thresholds, palette))
const total = computed(() => props.overview.cards.sites)
const healthRate = computed(() => percent(props.overview.cards.normal, total.value))
const option = computed(() => healthOption(slices.value, palette))
const rateChange = computed(() => {
  const base = props.overview.week_base
  return base ? rateDelta(props.overview.cards.normal, total.value, base.normal, base.sites) : null
})
const label = computed(() =>
  `网站健康结构：${slices.value.map(slice => `${slice.label} ${slice.value} 个`).join('，')}，健康率 ${healthRate.value}`,
)

function onSelect(params: { dataIndex: number }) {
  const slice = slices.value[params.dataIndex]
  if (slice) emit('pick', slice.status)
}
</script>

<template>
  <section class="chart-panel">
    <header class="chart-head">
      <div>
        <h3>健康结构</h3>
        <p class="chart-note">
          健康率 = 正常网站占比<template v-if="rateChange?.text">
            ，{{ rateChange.text }}
          </template>；点击分类筛选下方列表
        </p>
      </div>
    </header>
    <div class="health-body">
      <div class="donut">
        <BaseChart
          :option="option"
          :label="label"
          height="200px"
          @select="onSelect"
        />
        <div
          class="donut-center"
          aria-hidden="true"
        >
          <strong>{{ healthRate }}</strong>
          <span>健康率</span>
        </div>
      </div>
      <ul class="legend">
        <li
          v-for="slice in slices"
          :key="slice.key"
        >
          <button
            type="button"
            :class="{ selected: selected.includes(slice.status) }"
            :aria-pressed="selected.includes(slice.status)"
            :title="slice.hint"
            @click="emit('pick', slice.status)"
          >
            <span
              class="dot"
              :style="{ background: slice.color }"
            />
            <span class="legend-label">{{ slice.label }}</span>
            <strong>{{ slice.value.toLocaleString() }}</strong>
            <span class="legend-rate">{{ percent(slice.value, total) }}</span>
          </button>
          <span class="legend-hint">{{ slice.hint }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.health-body { display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: var(--zt-space-4); align-items: center; }
.donut { position: relative; }
.donut-center {
  position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;
  pointer-events: none;
}
.donut-center strong { font-size: 26px; color: var(--zt-ink-900); font-variant-numeric: tabular-nums; }
.donut-center span { font-size: 12px; color: var(--zt-ink-500); }
.legend { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.legend button {
  display: grid; grid-template-columns: 10px 1fr auto 52px; align-items: center; gap: 8px; width: 100%;
  padding: 4px 6px; border: 1px solid transparent; border-radius: var(--zt-radius); background: none;
  font: inherit; color: var(--zt-ink-700); cursor: pointer; text-align: left;
}
.legend button:hover { background: var(--zt-soft); }
.legend button.selected { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-5); }
.legend button:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.legend strong { color: var(--zt-ink-900); font-variant-numeric: tabular-nums; }
.legend-rate { color: var(--zt-ink-500); font-size: 12px; text-align: right; font-variant-numeric: tabular-nums; }
.legend-hint { display: block; padding-left: 24px; font-size: 12px; color: var(--zt-ink-500); }
.dot { width: 10px; height: 10px; border-radius: 2px; }
@media (max-width: 767px) {
  .health-body { grid-template-columns: minmax(0, 1fr); }
}
</style>
