<script setup lang="ts">
import type { TenderTotals } from '@/api/tender'
import { compactCount } from './statistics'

defineProps<{
  totals: TenderTotals | null
  totalsLoading: boolean
  hasReport: boolean
  rangeTotals: { total: number; days: number; dailyAvg: number }
  workload: number
}>()

const sharePct = (part?: number, whole?: number) => (!part || !whole ? '0.0%' : `${((part * 100) / whole).toFixed(1)}%`)
const shareNum = (part?: number, whole?: number) => (!part || !whole ? 0 : Math.min(100, (part * 100) / whole))
const count = (value?: number) => (value === undefined ? '—' : value.toLocaleString('zh-CN'))
</script>

<template>
  <div
    v-loading="totalsLoading && !totals"
    class="kpi-grid"
  >
    <div class="kpi-card kpi-card--main">
      <div class="kpi-head">
        <span>全库数据总量</span>
        <span class="kpi-badge">原始全表</span>
      </div>
      <strong
        class="kpi-value kpi-value--primary"
        :title="`完整数值：${count(totals?.total)}`"
      >{{ totals ? compactCount(totals.total) : '—' }}</strong>
      <span class="kpi-foot">{{ totals ? `${count(totals.total)} 条原始记录` : '正在统计中…' }}</span>
    </div>

    <div class="kpi-card">
      <div class="kpi-head">
        <span class="dot-label"><span class="dot dot--primary" />招标总量</span>
        <span class="kpi-pill kpi-pill--primary">{{ sharePct(totals?.purchaser, totals?.total) }}</span>
      </div>
      <strong
        class="kpi-value"
        :title="count(totals?.purchaser)"
      >{{ totals ? compactCount(totals.purchaser) : '—' }}</strong>
      <div class="progress-track">
        <div
          class="progress-fill progress-fill--primary"
          :style="{ width: `${shareNum(totals?.purchaser, totals?.total)}%` }"
        />
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-head">
        <span class="dot-label"><span class="dot dot--success" />中标总量</span>
        <span class="kpi-pill kpi-pill--success">{{ sharePct(totals?.winbid, totals?.total) }}</span>
      </div>
      <strong
        class="kpi-value"
        :title="count(totals?.winbid)"
      >{{ totals ? compactCount(totals.winbid) : '—' }}</strong>
      <div class="progress-track">
        <div
          class="progress-fill progress-fill--success"
          :style="{ width: `${shareNum(totals?.winbid, totals?.total)}%` }"
        />
      </div>
    </div>

    <div class="kpi-card">
      <div class="kpi-head">
        <span>区间接入合计</span>
        <span class="kpi-badge">{{ rangeTotals.days ? `${rangeTotals.days} 天` : '—' }}</span>
      </div>
      <strong
        class="kpi-value"
        :title="count(rangeTotals.total)"
      >{{ hasReport ? compactCount(rangeTotals.total) : '—' }}</strong>
      <span class="kpi-foot">{{ hasReport ? `日均 ${count(rangeTotals.dailyAvg)} 条` : '等待查询结果' }}</span>
    </div>

    <div class="kpi-card">
      <div class="kpi-head">
        <span>人工交付处理</span>
        <span class="kpi-pill kpi-pill--warn">场景暂 0</span>
      </div>
      <strong class="kpi-value">{{ hasReport ? count(workload) : '—' }}</strong>
      <span class="kpi-foot">信息化标签 · 基础字段各 {{ hasReport ? count(workload) : '—' }} 条</span>
    </div>
  </div>
</template>

<style scoped src="./tender-statistics.css"></style>
