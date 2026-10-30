<script setup lang="ts">
import { computed } from 'vue'

import type { CrawlerConfigReport } from '@/api/crawlerConfig'
import { BLANK_PROVINCE } from './report'

/** 所选这期配置的网站：点各省柱子打开，只看这个省。 */
const props = defineProps<{ report: CrawlerConfigReport; periodName: string; province: string }>()
const emit = defineEmits<{ close: [] }>()

const sites = computed(() => props.report.new_sites.filter(site => (site.province_name || BLANK_PROVINCE) === props.province))
</script>

<template>
  <el-drawer
    :model-value="Boolean(province)"
    :title="`${province} · ${periodName}配置的网站（${sites.length.toLocaleString()} 个）`"
    size="min(960px, 92vw)"
    @close="emit('close')"
  >
    <p class="sites__note">
      一行一个栏目；上线时间是爬虫同事在规则表里建这个栏目规则的日期（按网站一行的老信源是这个网站最早那条规则的日期）
    </p>
    <p
      v-if="!sites.length"
      class="sites__empty"
    >
      {{ province }}{{ periodName }}没有配置网站。
    </p>
    <el-table
      v-else
      :data="sites"
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
        prop="tag"
        label="栏目"
        min-width="160"
        show-overflow-tooltip
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
  </el-drawer>
</template>

<style scoped>
.sites__note { margin: 0 0 12px; color: var(--zt-ink-500); font-size: 12px; }
.sites__empty { margin: 0; padding: 28px 16px; color: var(--zt-ink-500); font-size: 13px; text-align: center; }
:deep(.el-table .cell) { font-variant-numeric: tabular-nums; }
</style>
