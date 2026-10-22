<script setup lang="ts">
import { computed, ref } from 'vue'

import type { CrawlerProvince } from '@/api/crawlerMonitoring'
import BaseChart from '@/components/charts/BaseChart.vue'
import { chartPalette } from '@/components/charts/echarts'
import { percent, provinceOption, sortProvinces, type ProvinceSort } from './charts'
import CrawlerProvinceTiles from './CrawlerProvinceTiles.vue'

const props = defineProps<{ provinces: CrawlerProvince[]; selected: string[] }>()
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

const VIEWS = [
  { value: 'bar', label: '柱状图' },
  { value: 'tiles', label: '卡片' },
] as const

const palette = chartPalette(getComputedStyle(document.documentElement))
const view = ref<(typeof VIEWS)[number]['value']>('bar')
const sort = ref<ProvinceSort>('stale')
const rows = computed(() => sortProvinces(props.provinces, sort.value))
const option = computed(() => provinceOption(rows.value, palette, props.selected, sort.value))
const metricName = computed(() => SORTS.find(item => item.value === sort.value)?.label ?? '')
const label = computed(() =>
  `省份分布：${rows.value.slice(0, 5).map(item => `${item.name} ${item.sites} 个，停更 ${item.stale} 个（${percent(item.stale, item.sites)}）`).join('；')}`,
)

function onSelect(params: { dataIndex: number }) {
  const item = rows.value[params.dataIndex]
  if (item?.sites) emit('pick', item.raw_names)
}
</script>

<template>
  <section class="chart-panel">
    <header class="chart-head">
      <div>
        <h3>省份分布</h3>
        <p class="chart-note">
          按省份字段的分类排列，31 个省级行政区以及全国、国央企都在其中，省份为空的网站算作国央企，「国家」算作全国。<template v-if="view === 'bar'">
            柱高和柱顶数字都是{{ metricName }}，切换排序即换指标；悬停看正常、关注、停更明细。点击柱子筛选下方列表
          </template><template v-else>
            大数字是停更网站数，色条是正常、关注、停更的占比。点击卡片筛选下方列表
          </template>
        </p>
      </div>
      <div class="chart-tools">
        <el-radio-group
          v-model="view"
          size="small"
          aria-label="省份展示方式"
        >
          <el-radio-button
            v-for="item in VIEWS"
            :key="item.value"
            :value="item.value"
          >
            {{ item.label }}
          </el-radio-button>
        </el-radio-group>
        <ul
          v-if="view === 'tiles'"
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
    <BaseChart
      v-if="view === 'bar'"
      :option="option"
      :label="label"
      height="340px"
      @select="onSelect"
    />
    <CrawlerProvinceTiles
      v-else
      :rows="rows"
      :selected="selected"
      @pick="names => emit('pick', names)"
    />
  </section>
</template>

<style scoped>
.chart-tools { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.province-legend { display: flex; gap: 12px; margin: 0; padding: 0; list-style: none; font-size: 12px; color: var(--zt-ink-500); }
.province-legend li { display: flex; align-items: center; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 2px; }
</style>
