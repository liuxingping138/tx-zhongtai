<script setup lang="ts">
import { computed } from 'vue'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'
import BaseChart from '@/components/charts/BaseChart.vue'
import { chartPalette } from '@/components/charts/echarts'
import { coverageOption } from './report'

/** 累计配置：覆盖率进度环加已配置、未配置、异常三个数。异常可以直接去信源管理核对。 */
const props = defineProps<{ report: CrawlerConfigReport; abnormalLink: { path: string; query: Record<string, string> } | null }>()

const palette = chartPalette(getComputedStyle(document.documentElement))
const ring = computed(() => coverageOption(props.report.totals, palette))
</script>

<template>
  <section
    class="coverage"
    aria-labelledby="coverage-title"
  >
    <h2 id="coverage-title">
      累计配置
    </h2>
    <div class="coverage__body">
      <div class="coverage__ring">
        <BaseChart
          :option="ring"
          :label="`覆盖率 ${report.totals.coverage}%：已配置 ${report.totals.online} 个，未配置 ${report.totals.pending} 个，异常 ${report.totals.abnormal} 个`"
          height="150px"
        />
        <div
          class="coverage__center"
          aria-hidden="true"
        >
          <strong>{{ report.totals.coverage }}<small>%</small></strong>
          <span>覆盖率</span>
        </div>
      </div>
      <dl class="coverage__list">
        <div>
          <dt><i class="dot dot--online" />已配置</dt>
          <dd>{{ report.totals.online.toLocaleString() }}</dd>
        </div>
        <div>
          <dt><i class="dot dot--pending" />未配置</dt>
          <dd>{{ report.totals.pending.toLocaleString() }}</dd>
        </div>
        <div>
          <dt><i class="dot dot--abnormal" />异常</dt>
          <dd>
            {{ report.totals.abnormal.toLocaleString() }}
            <router-link
              v-if="abnormalLink && report.totals.abnormal"
              :to="abnormalLink"
            >
              去核对
            </router-link>
          </dd>
        </div>
        <div class="coverage__total">
          <dt>信源网站</dt>
          <dd>{{ report.totals.total.toLocaleString() }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<style scoped>
.coverage { padding: 16px 20px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); min-width: 0; }
.coverage h2 { margin: 0 0 8px; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
.coverage__body { display: flex; align-items: center; gap: 24px; min-height: 230px; }
.coverage__ring { position: relative; width: 150px; flex: none; }
.coverage__center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
.coverage__center strong { color: var(--zt-ink-900); font-size: 28px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }
.coverage__center small { font-size: 14px; }
.coverage__center span { margin-top: 6px; color: var(--zt-ink-500); font-size: 12px; }
.coverage__list { flex: 1; margin: 0; }
.coverage__list > div { display: flex; justify-content: space-between; align-items: baseline; padding: 9px 0; border-bottom: 1px solid var(--zt-border); }
.coverage__list dt { display: flex; align-items: center; gap: 8px; color: var(--zt-ink-700); font-size: 13px; }
.coverage__list dd { margin: 0; color: var(--zt-ink-900); font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
.coverage__list dd a { margin-left: 8px; font-size: 12px; font-weight: 400; color: var(--zt-blue-600); }
.coverage__total { border-bottom: 0 !important; }
.coverage__total dt, .coverage__total dd { color: var(--zt-ink-500); font-size: 13px; font-weight: 400; }
.dot { width: 8px; height: 8px; border-radius: 2px; }
.dot--online { background: var(--zt-blue-600); }
.dot--pending { background: var(--zt-border); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--zt-ink-500) 35%, transparent); }
.dot--abnormal { background: var(--chart-stale); }
</style>
