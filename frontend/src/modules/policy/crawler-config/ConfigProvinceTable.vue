<script setup lang="ts">
import { MapLocation } from '@element-plus/icons-vue'
import { computed } from 'vue'

import type { ConfigProvince, CrawlerConfigReport } from '@/api/crawlerConfig'
import { sparkHeights } from './report'

/**
 * 分省情况：一张表同时看这个省所选周配置了多少、上周多少、近 12 周走势和累计覆盖。
 * 默认按所选周配置数从多到少，和每周给领导的「省份 / 配置网站数量」一致；点一行在下面只看这个省的明细。
 */
const props = defineProps<{ report: CrawlerConfigReport; weekName: string; selected: string }>()
const emit = defineEmits<{ select: [province: string] }>()

const rows = computed(() =>
  props.report.provinces
    .map(row => ({ ...row, previous: row.weekly.at(-2) ?? 0 }))
    .sort((a, b) => b.new - a.new || b.online - a.online))
const count = (_row: unknown, _column: unknown, value: number) => value.toLocaleString()
const summary = () => {
  const totals = props.report.totals
  const values = [totals.new, props.report.previous_new, '', totals.online, totals.total, `${totals.coverage}%`, totals.abnormal]
  return ['总计', ...values.map(value => (typeof value === 'number' ? value.toLocaleString() : value))]
}
const highlight = ({ row }: { row: ConfigProvince }) => (row.province_name === props.selected ? 'is-selected' : '')
const weeks = computed(() => props.report.trend.map(week => week.week_from.slice(5)))
</script>

<template>
  <section class="provinces">
    <header class="provinces__head">
      <el-icon aria-hidden="true">
        <MapLocation />
      </el-icon>
      <div>
        <h2>分省情况</h2>
        <p>按{{ weekName }}配置数量从多到少；点一行，下面只看这个省{{ weekName }}配置的网站</p>
      </div>
    </header>
    <el-table
      :data="rows"
      show-summary
      :summary-method="summary"
      :row-class-name="highlight"
      class="provinces__table"
      @row-click="(row: ConfigProvince) => emit('select', row.province_name === selected ? '' : row.province_name)"
    >
      <el-table-column
        prop="province_name"
        label="省份"
        min-width="120"
        fixed
      />
      <el-table-column
        prop="new"
        :label="`${weekName}配置`"
        width="110"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <strong
            v-if="row.new"
            class="provinces__new"
          >{{ row.new.toLocaleString() }}</strong>
          <span
            v-else
            class="provinces__zero"
          >—</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="previous"
        label="上周"
        width="90"
        align="right"
        sortable
        :formatter="count"
      />
      <el-table-column
        label="近 12 周"
        width="170"
      >
        <template #default="{ row }">
          <span
            class="spark"
            role="img"
            :aria-label="`${row.province_name}近 12 周配置：${row.weekly.join('、')}`"
          >
            <i
              v-for="(height, index) in sparkHeights(row.weekly)"
              :key="index"
              :title="`${weeks[index]} 起：${row.weekly[index]} 个`"
              :class="{ 'is-last': index === row.weekly.length - 1 }"
              :style="{ height: `${height}%` }"
            />
          </span>
        </template>
      </el-table-column>
      <el-table-column
        prop="online"
        label="已配置"
        width="100"
        align="right"
        sortable
        :formatter="count"
      />
      <el-table-column
        prop="total"
        label="信源网站"
        width="112"
        align="right"
        sortable
        :formatter="count"
      />
      <el-table-column
        prop="coverage"
        label="覆盖率"
        min-width="180"
        sortable
      >
        <template #default="{ row }">
          <el-progress
            :percentage="row.coverage"
            :stroke-width="8"
            color="var(--zt-blue-600)"
          />
        </template>
      </el-table-column>
      <el-table-column
        prop="abnormal"
        label="异常"
        width="80"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <span :class="row.abnormal ? 'provinces__abnormal' : 'provinces__zero'">{{ row.abnormal || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<style scoped>
.provinces { padding: 16px 20px 18px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); min-width: 0; }
.provinces__head { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px; }
.provinces__head > .el-icon { margin-top: 2px; font-size: 18px; color: var(--zt-blue-600); }
.provinces__head h2 { margin: 0; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
.provinces__head p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; }
.provinces__table { cursor: pointer; }
.provinces :deep(.el-table .cell) { font-variant-numeric: tabular-nums; }
.provinces :deep(.el-table__footer .cell) { font-weight: 600; color: var(--zt-ink-900); }
.provinces :deep(.el-table .is-selected td.el-table__cell) { background: var(--el-color-primary-light-9); }
.provinces :deep(.el-progress__text) { min-width: 46px; font-size: 13px !important; color: var(--zt-ink-900); }
.provinces__new { color: var(--chart-normal); font-size: 15px; }
.provinces__zero { color: var(--zt-ink-500); }
.provinces__abnormal { color: var(--chart-stale); font-weight: 600; }
.spark { display: flex; align-items: flex-end; gap: 3px; height: 24px; }
.spark i { flex: 1; min-height: 2px; border-radius: 1px; background: color-mix(in srgb, var(--chart-normal) 45%, transparent); }
.spark i.is-last { background: var(--chart-normal); }
</style>
