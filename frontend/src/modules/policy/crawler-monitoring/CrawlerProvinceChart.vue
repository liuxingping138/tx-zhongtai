<script setup lang="ts">
import { computed, ref } from 'vue'

import type { CrawlerProvince } from '@/api/crawlerMonitoring'
import { sortProvinces } from './charts'
import CrawlerProvinceRank from './CrawlerProvinceRank.vue'
import CrawlerProvinceTiles from './CrawlerProvinceTiles.vue'

const props = defineProps<{ provinces: CrawlerProvince[]; selected: string[] }>()
const emit = defineEmits<{ pick: [rawNames: string[]] }>()

const RANK_LEGEND = [
  { label: '正常及关注', color: 'var(--zt-blue-600)' },
  { label: '停更', color: 'var(--chart-stale)' },
]

const TILE_LEGEND = [
  { label: '正常', color: 'var(--chart-normal)' },
  { label: '关注', color: 'var(--chart-watch)' },
  { label: '停更', color: 'var(--chart-stale)' },
]

const VIEWS = [
  { value: 'rank', label: '水平排行' },
  { value: 'tiles', label: '卡片' },
] as const

const view = ref<(typeof VIEWS)[number]['value']>('rank')
const rows = computed(() => sortProvinces(props.provinces))
const legend = computed(() => (view.value === 'rank' ? RANK_LEGEND : TILE_LEGEND))
</script>

<template>
  <section class="chart-panel">
    <header class="chart-head">
      <div>
        <h3>省份分布</h3>
        <p class="chart-note">
          按网站总数从多到少排列，31 个省级行政区以及全国、国央企都在其中，省份为空的网站算作国央企，「国家」算作全国。<template v-if="view === 'rank'">
            悬停查看正常、关注、停更明细，点击省份筛选下方列表
          </template><template v-else>
            大数字是停更网站数，色条是正常、关注、停更的占比。点击卡片筛选下方列表
          </template>
        </p>
      </div>
      <div class="chart-tools">
        <ul
          class="province-legend"
          aria-hidden="true"
        >
          <li
            v-for="item in legend"
            :key="item.label"
          >
            <span
              class="dot"
              :style="{ background: item.color }"
            />{{ item.label }}
          </li>
        </ul>
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
      </div>
    </header>
    <CrawlerProvinceRank
      v-if="view === 'rank'"
      :rows="rows"
      :selected="selected"
      @pick="names => emit('pick', names)"
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
.dot { width: 8px; height: 8px; border-radius: 50%; }
</style>
