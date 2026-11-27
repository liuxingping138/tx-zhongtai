<script setup lang="ts">
import { computed, ref } from 'vue'

import type { ThinktankStatsGranularity, TrendPoint } from '@/api/thinktankStats'
import BaseChart from '@/components/charts/BaseChart.vue'
import { useChartPalette } from '@/components/charts/echarts'
import { buildConsumeTrendOption, buildProduceTrendOption } from './charts'

const props = defineProps<{
  trend: TrendPoint[]
  granularity: ThinktankStatsGranularity
  windowLabel: string
  loading: boolean
}>()

const GRAN_TEXT: Record<ThinktankStatsGranularity, string> = {
  day: '按日',
  week: '按周',
  month: '按月',
  quarter: '按季',
  year: '按年',
}

const palette = useChartPalette()
const activeTab = ref<'produce' | 'consume'>('produce')
const chartStyle = ref<'bar' | 'line'>('bar')

const option = computed(() =>
  activeTab.value === 'produce'
    ? buildProduceTrendOption(props.trend, chartStyle.value, palette.value)
    : buildConsumeTrendOption(props.trend, chartStyle.value, palette.value),
)

const totals = computed(() => ({
  uploads: props.trend.reduce((s, p) => s + p.total_uploads, 0),
  governance: props.trend.reduce((s, p) => s + p.governance, 0),
  previews: props.trend.reduce((s, p) => s + p.previews, 0),
  downloads: props.trend.reduce((s, p) => s + p.downloads, 0),
}))

const fmt = (n: number) => n.toLocaleString('zh-CN')
</script>

<template>
  <section
    class="tt-panel"
    :class="{ 'is-refreshing': loading }"
  >
    <div class="tt-panel__head">
      <div>
        <h2 class="tt-panel__title">
          知识生产与消费行为趋势
        </h2>
        <p class="tt-panel__sub">
          {{ GRAN_TEXT[granularity] }}聚合（{{ windowLabel }}）· 鼠标悬停查看各库拆解与治理/消费明细
        </p>
      </div>
      <div class="tt-ctrl__group">
        <div
          class="tt-seg"
          role="tablist"
          aria-label="趋势视角"
        >
          <button
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': activeTab === 'produce' }"
            @click="activeTab = 'produce'"
          >
            内容生产与治理
          </button>
          <button
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': activeTab === 'consume' }"
            @click="activeTab = 'consume'"
          >
            知识使用与消费
          </button>
        </div>
        <div
          class="tt-seg"
          role="tablist"
          aria-label="图表形态"
        >
          <button
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': chartStyle === 'bar' }"
            @click="chartStyle = 'bar'"
          >
            柱线组合
          </button>
          <button
            type="button"
            class="tt-seg__btn"
            :class="{ 'is-active': chartStyle === 'line' }"
            @click="chartStyle = 'line'"
          >
            平滑趋势
          </button>
        </div>
      </div>
    </div>

    <div class="tt-trend-legend">
      <template v-if="activeTab === 'produce'">
        <span class="tt-legend-item"><span class="tt-dot tt-dot--knowledge" />资料库上传</span>
        <span class="tt-legend-item"><span class="tt-dot tt-dot--reports" />报告库上传</span>
        <span class="tt-legend-item"><span class="tt-dot tt-dot--proposals" />方案库上传</span>
        <span class="tt-legend-item"><span class="tt-dot tt-dot--gov" />标签治理 / 编辑</span>
        <span class="tt-legend-total tabular">
          区间上传 <strong>{{ fmt(totals.uploads) }}</strong> 份 · 治理 <strong>{{ fmt(totals.governance) }}</strong> 次
        </span>
      </template>
      <template v-else>
        <span class="tt-legend-item"><span class="tt-dot tt-dot--knowledge" />在线预览</span>
        <span class="tt-legend-item"><span class="tt-dot tt-dot--reports" />原文件下载</span>
        <span class="tt-legend-item"><span class="tt-dot tt-dot--active" />去重活跃人数（右轴）</span>
        <span class="tt-legend-total tabular">
          区间预览 <strong>{{ fmt(totals.previews) }}</strong> 次 · 下载 <strong>{{ fmt(totals.downloads) }}</strong> 次
        </span>
      </template>
    </div>

    <BaseChart
      v-if="trend.length > 0"
      :option="option"
      label="智库生产与消费行为趋势图"
      height="268px"
    />
    <div
      v-else
      class="tt-empty"
    >
      <strong>该时间范围内暂无行为记录</strong>
      <p>尝试切换为「本季度」「今年以来」或「全部」查看更长时间跨度的上传、治理与查阅趋势。</p>
    </div>
  </section>
</template>

<style scoped src="./thinktank-statistics.css"></style>
