<script setup lang="ts">
import { DocumentAdd } from '@element-plus/icons-vue'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'

/** 本周新配置的网站明细。 */
defineProps<{ report: CrawlerConfigReport }>()
</script>

<template>
  <section class="new-sites">
    <header class="new-sites__head">
      <el-icon aria-hidden="true">
        <DocumentAdd />
      </el-icon>
      <div>
        <h2>本周新配置的网站</h2>
        <p>{{ report.new_sites.length ? `共 ${report.new_sites.length.toLocaleString()} 个，按省份、地市排列` : '上线时间在本周的网站' }}</p>
      </div>
    </header>
    <div
      v-if="!report.new_sites.length"
      class="new-sites__empty"
    >
      <el-icon aria-hidden="true">
        <DocumentAdd />
      </el-icon>
      <p>{{ report.counted ? '这一周还没有新配置的网站。' : `${report.report_start} 开始统计，之前配置的都算期初存量。` }}</p>
    </div>
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
.new-sites { padding: 16px 20px 18px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); min-width: 0; }
.new-sites__head { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 12px; }
.new-sites__head > .el-icon { margin-top: 2px; font-size: 18px; color: var(--chart-normal); }
.new-sites__head h2 { margin: 0; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
.new-sites__head p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; }
.new-sites__empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 28px 16px; color: var(--zt-ink-500); text-align: center; }
.new-sites__empty .el-icon { font-size: 28px; opacity: 0.5; }
.new-sites__empty p { margin: 0; max-width: 36em; font-size: 13px; line-height: 1.6; }
.new-sites :deep(.el-table .cell) { font-variant-numeric: tabular-nums; }
</style>
