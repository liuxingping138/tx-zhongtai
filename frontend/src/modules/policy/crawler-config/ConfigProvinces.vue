<script setup lang="ts">
import { computed, ref } from 'vue'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'
import ConfigProvinceWeekly from './ConfigProvinceWeekly.vue'

/** 分省明细：累计情况（标准表格，点表头排序）和每周配置数（省 × 周）两页。 */
const props = defineProps<{ report: CrawlerConfigReport; current: boolean; weekName: string }>()

const tab = ref<'total' | 'weekly'>('total')
const byNew = computed(() => [...props.report.provinces].sort((a, b) => b.new - a.new || b.total - a.total))
/** 数字列加千分位。 */
const count = (_row: unknown, _column: unknown, value: number) => value.toLocaleString()
const summary = () => {
  const totals = props.report.totals
  return ['总计', totals.total, totals.online, `${totals.coverage}%`, totals.pending, totals.abnormal, totals.new].map(value => value.toLocaleString())
}
</script>

<template>
  <section class="provinces">
    <header class="provinces__head">
      <h2>分省明细</h2>
      <el-radio-group
        v-model="tab"
        size="small"
        aria-label="分省明细"
      >
        <el-radio-button value="total">
          累计情况
        </el-radio-button>
        <el-radio-button value="weekly">
          每周配置数
        </el-radio-button>
      </el-radio-group>
    </header>

    <el-table
      v-if="tab === 'total'"
      :data="byNew"
      show-summary
      :summary-method="summary"
      :default-sort="{ prop: 'new', order: 'descending' }"
    >
      <el-table-column
        prop="province_name"
        label="省份"
        min-width="120"
        fixed
      />
      <el-table-column
        prop="total"
        :formatter="count"
        label="信源网站"
        width="110"
        align="right"
        sortable
      />
      <el-table-column
        prop="online"
        :formatter="count"
        label="已配置"
        width="110"
        align="right"
        sortable
      />
      <el-table-column
        prop="coverage"
        label="覆盖率"
        min-width="200"
        sortable
      >
        <template #default="{ row }">
          <el-progress
            :percentage="row.coverage"
            :stroke-width="10"
            color="var(--zt-blue-600)"
          />
        </template>
      </el-table-column>
      <el-table-column
        prop="pending"
        :formatter="count"
        label="未配置"
        width="110"
        align="right"
        sortable
      />
      <el-table-column
        prop="abnormal"
        label="异常"
        width="90"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <span :class="{ 'is-abnormal': row.abnormal }">{{ row.abnormal }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="new"
        :label="`${weekName}配置`"
        width="120"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <span :class="{ 'is-new': row.new }">{{ row.new }}</span>
        </template>
      </el-table-column>
    </el-table>

    <ConfigProvinceWeekly
      v-else
      :rows="byNew"
      :weeks="report.trend"
      :report-start="report.report_start"
      :current="current"
    />
  </section>
</template>

<style scoped>
.provinces { padding: 16px 20px 18px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); min-width: 0; }
.provinces__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.provinces__head h2 { margin: 0; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
.provinces :deep(.el-table .cell) { font-variant-numeric: tabular-nums; }
.provinces :deep(.el-table__footer .cell) { font-weight: 600; color: var(--zt-ink-900); }
.provinces :deep(.el-progress__text) { min-width: 48px; font-size: 13px !important; color: var(--zt-ink-900); }
.is-abnormal { color: var(--chart-stale); font-weight: 600; }
.is-new { color: var(--chart-normal); font-weight: 600; }
</style>
