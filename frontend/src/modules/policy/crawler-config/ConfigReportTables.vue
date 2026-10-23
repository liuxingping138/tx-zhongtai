<script setup lang="ts">
import type { CrawlerConfigReport } from '@/api/crawlerConfig'

/** 周报下半部分：分省统计（末行合计）和本周新增明细。 */
const props = defineProps<{ report: CrawlerConfigReport }>()

function totalRow({ rowIndex }: { rowIndex: number }): string {
  return rowIndex === props.report.provinces.length ? 'is-total' : ''
}
</script>

<template>
  <section class="tables__panel">
    <header class="tables__head">
      <h2>分省统计</h2>
      <p>信源表一行算一个栏目；没填省份的单列一行</p>
    </header>
    <el-table
      :data="[...report.provinces, { ...report.totals, province_name: '合计' }]"
      :row-class-name="totalRow"
    >
      <el-table-column
        prop="province_name"
        label="省份"
        min-width="130"
      />
      <el-table-column
        prop="total"
        label="栏目总数"
        width="100"
        align="right"
      />
      <el-table-column
        prop="online"
        label="已爬"
        width="90"
        align="right"
      />
      <el-table-column
        prop="pending"
        label="未爬"
        width="90"
        align="right"
      />
      <el-table-column
        prop="abnormal"
        label="异常"
        width="90"
        align="right"
      />
      <el-table-column
        prop="new"
        label="本周新增"
        width="100"
        align="right"
      />
      <el-table-column
        label="覆盖率"
        width="100"
        align="right"
      >
        <template #default="{ row }">
          {{ row.coverage }}%
        </template>
      </el-table-column>
    </el-table>
  </section>
  <section class="tables__panel">
    <header class="tables__head">
      <h2>本周新增明细</h2>
      <p>共 {{ report.new_sites.length.toLocaleString() }} 个</p>
    </header>
    <p
      v-if="!report.new_sites.length"
      class="tables__empty"
    >
      {{ report.counted ? '这一周没有新上线的栏目' : '这一周在统计起始周之前，不列新增' }}
    </p>
    <el-table
      v-else
      :data="report.new_sites"
      max-height="480"
    >
      <el-table-column
        prop="province_name"
        label="省份"
        width="100"
      />
      <el-table-column
        prop="city_name"
        label="地市"
        width="110"
      />
      <el-table-column
        prop="site_name"
        label="网站名称"
        min-width="240"
      />
      <el-table-column
        prop="site_code"
        label="网站编码"
        width="130"
      />
      <el-table-column
        prop="crawler_status"
        label="爬虫状态"
        width="90"
      />
      <el-table-column
        prop="online_date"
        label="上线时间"
        width="110"
      />
      <el-table-column
        label="链接"
        min-width="240"
      >
        <template #default="{ row }">
          <a
            v-if="row.url"
            :href="row.url"
            target="_blank"
            rel="noopener noreferrer"
          >{{ row.url }}</a>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<style scoped>
.tables__panel { padding: 14px 18px; min-width: 0; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); }
.tables__head { margin-bottom: 8px; }
.tables__head h2 { margin: 0; color: var(--zt-ink-900); font-size: 14px; font-weight: 600; }
.tables__head p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; }
.tables__empty { margin: 0; padding: 40px 0; color: var(--zt-ink-500); font-size: 13px; text-align: center; }
.tables__panel :deep(.el-table .cell) { font-variant-numeric: tabular-nums; }
.tables__panel :deep(.el-table .is-total td) { font-weight: 600; background: var(--zt-soft); }
</style>
