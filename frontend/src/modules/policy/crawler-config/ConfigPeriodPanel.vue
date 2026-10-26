<script setup lang="ts">
import { CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed } from 'vue'

import type { ConfigUnit, CrawlerConfigReport } from '@/api/crawlerConfig'
import BaseChart from '@/components/charts/BaseChart.vue'
import { chartPalette } from '@/components/charts/echarts'
import { UNITS, periodOption, periodRange, provinceOption, provinceTableText } from './report'

/**
 * 配置数量：上面按周、月、季度、年看各期配置了多少，点柱子换一期；
 * 下面就是这一期各省配置了多少（有几个省就几根柱），即每周汇报的那张表，可一键复制。点省份看这些网站。
 */
const props = defineProps<{ report: CrawlerConfigReport; periodName: string; loading: boolean }>()
const emit = defineEmits<{ unit: [unit: ConfigUnit]; period: [from: string]; province: [name: string] }>()

const palette = chartPalette(getComputedStyle(document.documentElement))
const periods = computed(() => periodOption(props.report.unit, props.report.periods, props.report.period_from, palette))
const provinces = computed(() => provinceOption(props.report.provinces, palette))
const range = computed(() => periodRange(props.report.unit, props.report.period_from, props.report.period_to))
const unitName = computed(() => UNITS.find(item => item.value === props.report.unit)?.name ?? '期')

function pickPeriod(params: { dataIndex: number }): void {
  const item = props.report.periods[params.dataIndex]
  if (item) emit('period', item.period_from)
}

function pickProvince(params: { dataIndex: number }): void {
  const item = props.report.provinces[params.dataIndex]
  if (item) emit('province', item.province_name)
}

async function copyTable(): Promise<void> {
  try {
    await navigator.clipboard.writeText(provinceTableText(props.report.provinces, props.report.new))
    ElMessage.success('已复制，可直接粘贴到 Excel 或微信')
  } catch {
    ElMessage.error('浏览器不允许复制，请用「下载报告」')
  }
}
</script>

<template>
  <section
    v-loading="loading"
    class="panel"
  >
    <header class="panel-head">
      <div>
        <h2>配置数量</h2>
        <p class="note">
          每{{ unitName }}新配置的网站数，按上线时间（爬虫同事建规则的日期）统计；深色是正在看的这{{ unitName }}，点柱子换一{{ unitName }}。
          {{ report.backfill_date }} 统一补填的 {{ report.baseline.toLocaleString() }} 个历史网站不计入任何一期
        </p>
      </div>
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
    </header>
    <BaseChart
      :option="periods"
      :label="`各期配置网站数量：${report.periods.map(item => `${periodRange(report.unit, item.period_from, item.period_to)} ${item.new} 个`).join('，')}`"
      height="220px"
      @select="pickPeriod"
    />

    <div class="divider" />

    <header class="panel-head">
      <div>
        <h3>{{ periodName }}各省配置 <span class="range">{{ range }} · 共 {{ report.new.toLocaleString() }} 个</span></h3>
        <p class="note">
          有配置的省份才列出，按数量从多到少；点柱子查看这个省配置的网站
        </p>
      </div>
      <el-button
        :icon="CopyDocument"
        size="small"
        :disabled="!report.provinces.length"
        @click="copyTable"
      >
        复制表格
      </el-button>
    </header>
    <p
      v-if="!report.provinces.length"
      class="empty"
    >
      {{ periodName }}还没有配置网站。爬虫同事更新规则表后，每天 18:00 自动同步进来。
    </p>
    <BaseChart
      v-else
      :option="provinces"
      :label="`${periodName}各省配置网站数量：${report.provinces.map(item => `${item.province_name} ${item.new} 个`).join('，')}`"
      height="260px"
      @select="pickProvince"
    />
  </section>
</template>

<style scoped>
.panel { padding: var(--zt-space-3) var(--zt-space-4) var(--zt-space-4); background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); min-width: 0; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--zt-space-3); flex-wrap: wrap; margin-bottom: var(--zt-space-2); }
.panel-head h2, .panel-head h3 { margin: 0; font-size: 14px; font-weight: 600; color: var(--zt-ink-900); }
.range { margin-left: 8px; font-weight: 400; color: var(--zt-ink-500); font-size: 13px; font-variant-numeric: tabular-nums; }
.note { margin: 4px 0 0; font-size: 12px; line-height: 1.6; color: var(--zt-ink-500); }
.divider { height: 1px; margin: var(--zt-space-3) 0 var(--zt-space-4); background: var(--zt-border); }
.empty { margin: 0; padding: 40px 16px; color: var(--zt-ink-500); font-size: 13px; text-align: center; }
</style>
