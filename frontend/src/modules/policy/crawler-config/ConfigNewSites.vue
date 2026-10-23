<script setup lang="ts">
import { DocumentAdd } from '@element-plus/icons-vue'
import { computed } from 'vue'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'

/** 所选周配置的网站明细；分省表点了某个省时只看这个省。 */
const props = defineProps<{ report: CrawlerConfigReport; weekName: string; province: string }>()
const emit = defineEmits<{ clear: [] }>()

const sites = computed(() =>
  props.province ? props.report.new_sites.filter(site => site.province_name === props.province) : props.report.new_sites)
</script>

<template>
  <section class="sites">
    <header class="sites__head">
      <el-icon aria-hidden="true">
        <DocumentAdd />
      </el-icon>
      <div class="sites__title">
        <h2>{{ weekName }}配置的网站</h2>
        <p>共 {{ sites.length.toLocaleString() }} 个，上线时间是爬虫同事在规则表里配置它的日期</p>
      </div>
      <el-tag
        v-if="province"
        closable
        @close="emit('clear')"
      >
        只看 {{ province }}
      </el-tag>
    </header>
    <p
      v-if="!sites.length"
      class="sites__empty"
    >
      {{ province ? `${province}${weekName}没有配置网站。` : `${weekName}还没有配置网站。爬虫同事更新规则表后，每天 18:00 会自动同步进来。` }}
    </p>
    <el-table
      v-else
      :data="sites"
      max-height="520"
    >
      <el-table-column
        prop="province_name"
        label="省份"
        width="110"
      />
      <el-table-column
        prop="city_name"
        label="地市"
        width="110"
      />
      <el-table-column
        prop="site_name"
        label="网站名称"
        min-width="220"
      />
      <el-table-column
        prop="site_code"
        label="网站编码"
        width="130"
      />
      <el-table-column
        prop="online_date"
        label="上线时间"
        width="110"
      />
      <el-table-column
        prop="crawler_status"
        label="爬虫状态"
        width="90"
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
.sites { padding: 16px 20px 18px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); min-width: 0; }
.sites__head { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 12px; }
.sites__head > .el-icon { margin-top: 2px; font-size: 18px; color: var(--chart-normal); }
.sites__title { flex: 1; }
.sites__head h2 { margin: 0; color: var(--zt-ink-900); font-size: 15px; font-weight: 600; }
.sites__head p { margin: 4px 0 0; color: var(--zt-ink-500); font-size: 12px; }
.sites__empty { margin: 0; padding: 28px 16px; color: var(--zt-ink-500); font-size: 13px; text-align: center; }
.sites :deep(.el-table .cell) { font-variant-numeric: tabular-nums; }
</style>
