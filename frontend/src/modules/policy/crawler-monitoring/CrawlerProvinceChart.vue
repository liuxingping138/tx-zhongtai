<script setup lang="ts">
import { computed, ref } from 'vue'

import type { CrawlerProvince } from '@/api/crawlerMonitoring'
import BaseChart from '@/components/charts/BaseChart.vue'
import { chartPalette } from '@/components/charts/echarts'
import { percent, provinceAxisMax, provinceColumns, provinceOption, sortProvinces, type ProvinceSort } from './charts'

const props = defineProps<{ provinces: CrawlerProvince[] }>()
const emit = defineEmits<{ pick: [rawNames: string[]] }>()

const SORTS: { value: ProvinceSort; label: string }[] = [
  { value: 'stale', label: '停更数' },
  { value: 'rate', label: '停更率' },
  { value: 'sites', label: '网站数' },
]
const LEGEND = [
  { label: '正常', color: 'var(--chart-normal)' },
  { label: '关注', color: 'var(--chart-watch)' },
  { label: '停更', color: 'var(--chart-stale)' },
]

const palette = chartPalette(getComputedStyle(document.documentElement))
const sort = ref<ProvinceSort>('stale')
const rows = computed(() => sortProvinces(props.provinces, sort.value))
const columns = computed(() => provinceColumns(rows.value))
const axisMax = computed(() => provinceAxisMax(rows.value))
const height = computed(() => `${Math.max(...columns.value.map(column => column.length), 1) * 28 + 28}px`)
const label = computed(() =>
  `省份分布：${rows.value.slice(0, 5).map(item => `${item.name} ${item.sites} 个，停更 ${item.stale} 个（${percent(item.stale, item.sites)}）`).join('；')}`,
)

function optionFor(column: CrawlerProvince[]) {
  return provinceOption(column, palette, axisMax.value)
}

function onSelect(column: CrawlerProvince[], params: { dataIndex: number }) {
  // 图里是倒序画的，dataIndex 要换回排序后的位置。
  const item = column[column.length - 1 - params.dataIndex]
  if (item?.raw_names.length) emit('pick', item.raw_names)
}
</script>

<template>
  <section class="chart-panel">
    <header class="chart-head">
      <div>
        <h3>省份分布</h3>
        <p class="chart-note">
          按省份字段的分类排列，32 个省级行政区以及香港、澳门、全国、国央企都在其中；同一分类的不同写法已合并。两列共用同一坐标，条长按网站数，条尾数字是停更数。点击条形筛选下方列表
        </p>
      </div>
      <div class="chart-tools">
        <ul
          class="province-legend"
          aria-hidden="true"
        >
          <li
            v-for="item in LEGEND"
            :key="item.label"
          >
            <span
              class="dot"
              :style="{ background: item.color }"
            />{{ item.label }}
          </li>
        </ul>
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
      </div>
    </header>
    <div class="province-columns">
      <BaseChart
        v-for="(column, index) in columns"
        :key="`${sort}-${index}`"
        :option="optionFor(column)"
        :label="label"
        :height="height"
        @select="params => onSelect(column, params)"
      />
    </div>
  </section>
</template>

<style scoped>
.chart-tools { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.province-legend { display: flex; gap: 12px; margin: 0; padding: 0; list-style: none; font-size: 12px; color: var(--zt-ink-500); }
.province-legend li { display: flex; align-items: center; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 2px; }
.province-columns { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 4px 24px; }
@media (max-width: 767px) {
  .province-columns { grid-template-columns: minmax(0, 1fr); }
}
</style>
