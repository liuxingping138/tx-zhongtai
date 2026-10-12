<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { getCrawlerSiteTrend, type CrawlerSiteRef, type CrawlerTrendPoint } from '@/api/crawlerMonitoringV2'
import { errorMessage } from '@/api/errors'
import BaseChart from '@/components/charts/BaseChart.vue'
import { chartPalette } from '@/components/charts/echarts'
import { siteTrendOption, siteTrendSummary } from './charts'

const props = defineProps<{ site: CrawlerSiteRef }>()

const SITE_TREND_DAYS = 90
const SITE_TREND_ERROR = '暂时无法获取该网站的采集曲线。'
const palette = chartPalette(getComputedStyle(document.documentElement))
const points = ref<CrawlerTrendPoint[]>([])
const loading = ref(false)
const error = ref('')
let sequence = 0

const option = computed(() => siteTrendOption(points.value, palette))
const summary = computed(() => siteTrendSummary(points.value))

async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const result = await getCrawlerSiteTrend(props.site, SITE_TREND_DAYS)
    if (current === sequence) points.value = result.items
  } catch (cause) {
    if (current === sequence) error.value = errorMessage(cause, SITE_TREND_ERROR)
  } finally {
    if (current === sequence) loading.value = false
  }
}

watch(() => [props.site.site_name, props.site.province_name, props.site.city_name], () => { void load() }, { immediate: true })
</script>

<template>
  <section
    v-loading="loading"
    class="site-trend"
  >
    <h3>近 {{ SITE_TREND_DAYS }} 天采集量</h3>
    <p
      v-if="error"
      class="site-trend-note"
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
    </p>
    <template v-else-if="points.length">
      <p class="site-trend-note">
        {{ summary }}；浅色柱为周末
      </p>
      <BaseChart
        :option="option"
        :label="`该网站采集曲线：${summary}`"
        height="180px"
      />
    </template>
  </section>
</template>

<style scoped>
.site-trend { margin-top: var(--zt-space-6); min-height: 80px; }
.site-trend h3 { margin: 0; font-size: 14px; font-weight: 600; color: var(--zt-ink-900); }
.site-trend-note { margin: 4px 0 var(--zt-space-2); font-size: 12px; color: var(--zt-ink-500); }
</style>
