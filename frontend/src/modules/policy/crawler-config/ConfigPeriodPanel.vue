<script setup lang="ts">
import { computed } from 'vue'

import type { ConfigUnit, CrawlerConfigReport } from '@/api/crawlerConfig'
import BaseChart from '@/components/charts/BaseChart.vue'
import { useChartPalette } from '@/components/charts/echarts'
import { UNITS, adjacentPeriods, isFuture, periodOption, periodRange } from './report'

/** 配置数量：按周（近 12 周）、月（今年 12 个月）、季度（今年四个季度）、年看各期配置了多少；点柱子换到那一期并弹出各省配置。 */
const props = defineProps<{ report: CrawlerConfigReport; periodName: string; loading: boolean }>()
const emit = defineEmits<{ unit: [unit: ConfigUnit]; period: [from: string]; provinces: [] }>()

const palette = useChartPalette()
const periods = computed(() => periodOption(props.report.unit, props.report.periods, props.report.period_from, props.report.current_from, palette.value))
const unitName = computed(() => UNITS.find(item => item.value === props.report.unit)?.name ?? '期')

function pickPeriod(params: { dataIndex: number }): void {
  const item = props.report.periods[params.dataIndex]
  if (item && !isFuture(props.report, item.period_from)) emit('period', item.period_from)
}

// 上一期 / 下一期按钮：点柱子键盘够不着，图表旁边给一对按钮换期。
const adjacent = computed(() => adjacentPeriods(props.report))
const previous = computed(() => adjacent.value.previous)
const next = computed(() => adjacent.value.next)
</script>

<template>
  <section
    class="panel"
    :class="{ 'is-refreshing': loading }"
  >
    <header class="panel-head">
      <div>
        <h2>配置数量</h2>
        <p class="note">
          每{{ unitName }}新配置的网站数，按上线时间（爬虫同事建规则的日期）统计；深色是正在看的这{{ unitName }}，点柱子查看那一{{ unitName }}各省配置。
          {{ report.backfill_date }} 统一补填的 {{ report.baseline.toLocaleString() }} 个历史网站不计入任何一期
        </p>
      </div>
      <div class="tools">
        <el-button
          size="small"
          :disabled="!previous"
          @click="previous && emit('period', previous.period_from)"
        >
          上一{{ unitName }}
        </el-button>
        <el-button
          size="small"
          :disabled="!next"
          @click="next && emit('period', next.period_from)"
        >
          下一{{ unitName }}
        </el-button>
        <el-button
          size="small"
          @click="emit('provinces')"
        >
          {{ periodName }}各省明细
        </el-button>
        <el-radio-group
          :model-value="report.unit"
          size="small"
          aria-label="统计粒度"
          @change="(value: string | number | boolean | undefined) => emit('unit', value as ConfigUnit)"
        >
          <el-radio-button
            v-for="item in UNITS"
            :key="item.value"
            :value="item.value"
          >
            {{ item.label }}
          </el-radio-button>
        </el-radio-group>
      </div>
    </header>
    <BaseChart
      :option="periods"
      :label="`各期配置网站数量：${report.periods.map(item => `${periodRange(report.unit, item.period_from, item.period_to)} ${item.new} 个`).join('，')}`"
      height="220px"
      @select="pickPeriod"
    />
  </section>
</template>

<style scoped>
.panel { padding: 16px 20px; background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: 12px; box-shadow: var(--zt-shadow); min-width: 0; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: nowrap; margin-bottom: 10px; }
.panel-head > :first-child { flex: 1; min-width: 0; }
.tools { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; flex-shrink: 0; }
.panel-head h2 { margin: 0; font-size: 15px; font-weight: 650; color: var(--zt-ink-900); }
.note { margin: 4px 0 0; font-size: 12px; line-height: 1.6; color: var(--zt-ink-500); }
@media (max-width: 1024px) {
  .panel-head { flex-wrap: wrap; }
}
</style>
