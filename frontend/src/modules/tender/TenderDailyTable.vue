<script setup lang="ts">
import { computed } from 'vue'
import type { TenderPoint } from '@/api/tender'

const props = withDefaults(
  defineProps<{
    daily: TenderPoint[]
    loading?: boolean
    asOf?: string
  }>(),
  {
    loading: false,
    asOf: '',
  },
)

const count = (value?: number) => (value === undefined ? '—' : value.toLocaleString('zh-CN'))
const formatTime = (iso?: string) => (iso ? iso.replace('T', ' ').slice(0, 19) : '—')

const totalIntake = computed(() =>
  props.daily.reduce((sum, item) => sum + (item.purchaser || 0) + (item.winbid || 0), 0),
)
</script>

<template>
  <section class="panel daily-panel">
    <header class="panel-head">
      <div>
        <div class="title-wrap">
          <span class="google-badge-dot" />
          <h2>每日接入统计明细</h2>
        </div>
        <p class="panel-note">
          统计口径时间：{{ formatTime(asOf) }}
        </p>
      </div>
      <div class="head-meta">
        <span class="meta-pill">共 {{ daily.length }} 天</span>
        <span class="meta-pill meta-pill--highlight">区间接入 {{ count(totalIntake) }} 条</span>
      </div>
    </header>

    <div class="table-wrap">
      <el-table
        :data="daily"
        :class="{ 'is-refreshing': loading }"
        stripe
        max-height="295"
        empty-text="所选日期暂无每日数据"
        class="data-table google-data-table"
      >
        <el-table-column
          prop="date"
          label="采集日期"
          min-width="118"
        >
          <template #default="{ row }">
            <span class="date-cell tabular">{{ row.date }}</span>
          </template>
        </el-table-column>

        <el-table-column
          label="招标接入"
          align="right"
          min-width="100"
        >
          <template #default="{ row }">
            <span class="num-cell num-cell--primary tabular">{{ count(row.purchaser) }}</span>
          </template>
        </el-table-column>

        <el-table-column
          label="中标接入"
          align="right"
          min-width="100"
        >
          <template #default="{ row }">
            <span class="num-cell num-cell--success tabular">{{ count(row.winbid) }}</span>
          </template>
        </el-table-column>

        <el-table-column
          label="当日接入合计"
          align="right"
          min-width="110"
        >
          <template #default="{ row }">
            <strong class="num-cell num-cell--total tabular">{{ count(row.purchaser + row.winbid) }}</strong>
          </template>
        </el-table-column>

        <el-table-column
          label="信息化标签"
          align="right"
          min-width="96"
        >
          <template #default="{ row }">
            <span
              v-if="row.tagged > 0"
              class="work-pill work-pill--ai tabular"
            >{{ count(row.tagged) }}</span>
            <span
              v-else
              class="work-pill work-pill--zero"
            >0</span>
          </template>
        </el-table-column>

        <el-table-column
          label="基础补充"
          align="right"
          min-width="96"
        >
          <template #default="{ row }">
            <span
              v-if="row.enriched > 0"
              class="work-pill work-pill--teal tabular"
            >{{ count(row.enriched) }}</span>
            <span
              v-else
              class="work-pill work-pill--zero"
            >0</span>
          </template>
        </el-table-column>

        <el-table-column
          prop="scenario"
          label="场景补充"
          align="right"
          min-width="84"
        >
          <template #default="{ row }">
            <span
              v-if="row.scenario > 0"
              class="work-pill work-pill--info tabular"
            >{{ count(row.scenario) }}</span>
            <span
              v-else
              class="work-pill work-pill--muted"
            >—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: var(--zt-space-4) var(--zt-space-6);
  background: var(--zt-panel);
  border: 1px solid var(--zt-border);
  border-radius: 12px;
  box-shadow: var(--zt-shadow);
  min-width: 0;
}
.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--zt-space-3);
  flex-wrap: nowrap;
  margin-bottom: var(--zt-space-3);
}
.panel-head > :first-child {
  flex: 1 1 0;
  min-width: 0;
}
.panel-head > :last-child:not(:first-child) {
  flex-shrink: 0;
  white-space: nowrap;
}
.title-wrap {
  display: flex;
  align-items: center;
  gap: var(--zt-space-2);
}
.google-badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--zt-blue-600);
}
.panel-head h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  color: var(--zt-ink-900);
}
.panel-note {
  margin: var(--zt-space-1) 0 0;
  font-size: 12px;
  color: var(--zt-ink-500);
  line-height: 1.5;
}
.head-meta {
  display: flex;
  align-items: center;
  gap: var(--zt-space-2);
  flex-wrap: nowrap;
}
.meta-pill {
  padding: 2px var(--zt-space-2);
  border-radius: 999px;
  font-size: 12px;
  background: var(--zt-surface-subtle);
  color: var(--zt-ink-700);
  border: 1px solid var(--zt-border);
}
.meta-pill--highlight {
  background: var(--zt-soft);
  color: var(--zt-blue-600);
  font-weight: 600;
  border-color: var(--zt-border-strong);
}
.table-wrap {
  position: relative;
}
.date-cell {
  font-weight: 550;
  color: var(--zt-ink-900);
}
.num-cell {
  font-size: 12.5px;
}
.num-cell--primary {
  color: var(--zt-blue-600);
  font-weight: 550;
}
.num-cell--success {
  color: var(--chart-normal);
  font-weight: 550;
}
.num-cell--total {
  color: var(--zt-ink-900);
  font-weight: 650;
}
.work-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px var(--zt-space-2);
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
}
.work-pill--ai {
  background: var(--zt-ai-soft);
  color: var(--zt-ai-text);
  border: 1px solid var(--zt-ai-line);
}
.work-pill--teal {
  background: var(--zt-teal-soft);
  color: var(--zt-teal-text);
  border: 1px solid var(--zt-teal-line);
}
.work-pill--info {
  background: var(--el-color-primary-light-9);
  color: var(--zt-blue-600);
  border: 1px solid var(--el-color-primary-light-7);
}
.work-pill--zero {
  background: var(--zt-surface-subtle);
  color: var(--zt-ink-500);
  border: 1px solid var(--zt-divider);
}
.work-pill--muted {
  color: var(--zt-ink-500);
  font-weight: 400;
}
.tabular {
  font-variant-numeric: tabular-nums;
}
:deep(.google-data-table) {
  --el-table-header-bg-color: var(--zt-table-head);
  --el-table-row-hover-bg-color: var(--zt-row-hover);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--zt-divider);
}
:deep(.google-data-table th.el-table__cell) {
  font-weight: 600;
  color: var(--zt-ink-700);
  font-size: 12px;
}
:deep(.google-data-table td.el-table__cell) {
  padding: var(--zt-space-2) 0;
}
</style>
