<script setup lang="ts">
import { computed, ref } from 'vue'

import type { CrawlerProvince } from '@/api/crawlerMonitoringV2'
import BaseChart from '@/components/charts/BaseChart.vue'
import { chartPalette } from '@/components/charts/echarts'
import { PROVINCE_LIMIT, RATE_MIN_SITES, percent, provinceOption, sortProvinces, type ProvinceSort } from './charts'

const props = defineProps<{ provinces: CrawlerProvince[] }>()
const emit = defineEmits<{ pick: [rawNames: string[]] }>()

const SORTS: { value: ProvinceSort; label: string }[] = [
  { value: 'stale', label: '停更数' },
  { value: 'rate', label: '停更率' },
  { value: 'sites', label: '网站数' },
]

const palette = chartPalette(getComputedStyle(document.documentElement))
const sort = ref<ProvinceSort>('stale')
const rows = computed(() => sortProvinces(props.provinces, sort.value))
const option = computed(() => provinceOption(rows.value, palette))
const label = computed(() =>
  `省份分布：${rows.value.slice(0, 5).map(item => `${item.name} ${item.sites} 个，停更 ${item.stale} 个（${percent(item.stale, item.sites)}）`).join('；')}`,
)
const height = computed(() => `${Math.max(rows.value.length, 5) * 26 + 48}px`)

function onSelect(params: { dataIndex: number }) {
  // 图里是倒序画的，dataIndex 要换回排序后的位置。
  const item = rows.value[rows.value.length - 1 - params.dataIndex]
  if (item) emit('pick', item.raw_names)
}
</script>

<template>
  <section class="chart-panel">
    <header class="chart-head">
      <div>
        <h3>省份分布</h3>
        <p class="chart-note">
          前 {{ PROVINCE_LIMIT }} 个省份；同一省份的不同写法已合并<template v-if="sort === 'rate'">
            ，按停更率只看网站不少于 {{ RATE_MIN_SITES }} 个的省份
          </template>；点击条形筛选下方列表
        </p>
      </div>
      <el-radio-group
        v-model="sort"
        size="small"
        aria-label="省份排序方式"
      >
        <el-radio-button
          v-for="item in SORTS"
          :key="item.value"
          :value="item.value"
        >
          按{{ item.label }}
        </el-radio-button>
      </el-radio-group>
    </header>
    <BaseChart
      :option="option"
      :label="label"
      :height="height"
      @select="onSelect"
    />
  </section>
</template>
