<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter, type RouteLocationRaw } from 'vue-router'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'
import BaseChart from '@/components/charts/BaseChart.vue'
import { chartPalette } from '@/components/charts/echarts'
import { BLANK_PROVINCE, statusOption, statusRows } from './report'

/**
 * 分省爬虫状态：信源表按省份透视已爬、未爬、异常。默认堆叠柱图（柱高是信源总数，按总数从多到少），可切成表格（按省份编码排，和 Excel 透视一样）。
 * 有信源管理权限时，点柱子、点表格里已爬、异常、合计的数字去信源管理看是哪些网站（未爬含状态为空的，信源管理筛不出空值，不做链接）。
 */
const props = defineProps<{ report: CrawlerConfigReport; sourcesLink: ((status: string, province: string) => RouteLocationRaw) | null }>()

const VIEWS = [
  { value: 'chart', label: '图表' },
  { value: 'table', label: '表格' },
] as const
const router = useRouter()
const palette = chartPalette(getComputedStyle(document.documentElement))
const view = ref<(typeof VIEWS)[number]['value']>('chart')
const rows = computed(() => statusRows(props.report.status))
const option = computed(() => statusOption(rows.value, palette))

function pickProvince(params: { dataIndex: number }): void {
  const row = rows.value[params.dataIndex]
  if (row && props.sourcesLink && row.province_name !== BLANK_PROVINCE) void router.push(props.sourcesLink('', row.province_name))
}

const COLUMNS = [
  { key: 'online', label: '已爬', status: '已爬' },
  { key: 'pending', label: '未爬', status: null },
  { key: 'abnormal', label: '异常', status: '异常' },
  { key: 'total', label: '合计', status: '' },
] as const
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <div>
        <h2>分省爬虫状态</h2>
        <p class="note">
          <template v-if="view === 'chart'">
            柱高是这个省的信源网站总数，深蓝已爬（柱顶数字）、红色异常、浅蓝未爬；按总数从多到少，悬停看覆盖率{{ sourcesLink ? '，点柱子到信源管理看这个省的网站' : '' }}
          </template>
          <template v-else>
            信源表按省份透视爬虫状态，和在 Excel 里透视一样{{ sourcesLink ? '；点数字到信源管理查看对应网站' : '' }}
          </template>
        </p>
      </div>
      <el-radio-group
        v-model="view"
        size="small"
        aria-label="分省展示方式"
      >
        <el-radio-button
          v-for="item in VIEWS"
          :key="item.value"
          :value="item.value"
        >
          {{ item.label }}
        </el-radio-button>
      </el-radio-group>
    </header>
    <BaseChart
      v-if="view === 'chart'"
      :option="option"
      :label="`分省爬虫状态：${rows.slice(0, 5).map(row => `${row.province_name} 共 ${row.total} 个，已爬 ${row.online} 个`).join('；')}`"
      height="360px"
      @select="pickProvince"
    />
    <el-table
      v-else
      :data="report.status"
      show-summary
      :summary-method="() => ['总计', ...COLUMNS.map(column => report.totals[column.key].toLocaleString())]"
      class="status-table"
    >
      <el-table-column
        prop="province_name"
        label="省份"
        min-width="140"
      />
      <el-table-column
        v-for="column in COLUMNS"
        :key="column.key"
        :prop="column.key"
        :label="column.label"
        min-width="100"
        align="right"
        sortable
      >
        <template #default="{ row }">
          <router-link
            v-if="sourcesLink && column.status !== null && row[column.key] && row.province_name !== BLANK_PROVINCE"
            :to="sourcesLink(column.status, row.province_name)"
            class="count-link"
          >
            {{ row[column.key].toLocaleString() }}
          </router-link>
          <span
            v-else
            :class="{ zero: !row[column.key] }"
          >{{ row[column.key].toLocaleString() }}</span>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<style scoped>
.panel { padding: var(--zt-space-3) var(--zt-space-4) var(--zt-space-4); background: var(--zt-panel); border: 1px solid var(--zt-border); border-radius: var(--zt-radius); min-width: 0; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--zt-space-3); flex-wrap: wrap; margin-bottom: var(--zt-space-2); }
.panel-head h2 { margin: 0; font-size: 14px; font-weight: 600; color: var(--zt-ink-900); }
.note { margin: 4px 0 0; font-size: 12px; color: var(--zt-ink-500); }
.status-table :deep(.cell) { font-variant-numeric: tabular-nums; }
.status-table :deep(.el-table__footer .cell) { font-weight: 600; color: var(--zt-ink-900); }
.count-link { color: var(--zt-blue-600); text-decoration: none; }
.count-link:hover { text-decoration: underline; }
.zero { color: var(--zt-ink-400); }
</style>
