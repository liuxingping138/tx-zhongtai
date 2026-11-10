<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { getCrawlerTrend, type CrawlerTrendDays, type CrawlerTrendPoint } from '@/api/crawlerMonitoring'
import { errorMessage } from '@/api/errors'
import BaseChart from '@/components/charts/BaseChart.vue'
import { useChartPalette } from '@/components/charts/echarts'
import { TREND_RANGES, trendOption, trendSummary } from './charts'

const TREND_ERROR = '暂时无法获取采集趋势，请稍后重试。'
const UNIT_NOTE = { day: '按天', week: '按周，柱高为日均', month: '按月，柱高为日均' } as const

const palette = useChartPalette()
const days = ref<CrawlerTrendDays>(30)
const unitNote = computed(() => UNIT_NOTE[TREND_RANGES.find(item => item.value === days.value)?.unit ?? 'day'])
const points = ref<CrawlerTrendPoint[]>([])
const dateTo = ref('')
const loading = ref(false)
const error = ref('')
let sequence = 0

const option = computed(() => trendOption(points.value, days.value, palette.value))
const summary = computed(() => trendSummary(points.value, days.value))

async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const result = await getCrawlerTrend(days.value)
    if (current !== sequence) return
    points.value = result.items
    dateTo.value = result.date_to
  } catch (cause) {
    if (current === sequence) error.value = errorMessage(cause, TREND_ERROR)
  } finally {
    if (current === sequence) loading.value = false
  }
}

onMounted(() => { void load() })
defineExpose({ load })
</script>

<template>
  <section
    v-loading="loading"
    class="chart-panel"
  >
    <header class="chart-head">
      <div>
        <h3>采集趋势</h3>
        <p class="chart-note">
          {{ summary }}<template v-if="dateTo">
            （{{ unitNote }}，截至 {{ dateTo }}）
          </template>
        </p>
      </div>
      <el-radio-group
        v-model="days"
        size="small"
        aria-label="趋势时间范围"
        @change="load"
      >
        <el-radio-button
          v-for="range in TREND_RANGES"
          :key="range.value"
          :value="range.value"
        >
          {{ range.label }}
        </el-radio-button>
      </el-radio-group>
    </header>
    <div
      v-if="error"
      class="chart-error"
      role="alert"
    >
      {{ error }}
      <el-button
        link
        type="primary"
        @click="load"
      >
        重试
      </el-button>
    </div>
    <BaseChart
      v-else
      :option="option"
      :label="`采集趋势图：${summary}`"
      height="300px"
    />
  </section>
</template>
