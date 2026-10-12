<script setup lang="ts">
import { computed, ref } from 'vue'

import type { CrawlerProvince } from '@/api/crawlerMonitoring'
import { provinceSelected, provinceTile, sortProvinces, type ProvinceSort } from './charts'

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

const sort = ref<ProvinceSort>('stale')
const tiles = computed(() => sortProvinces(props.provinces, sort.value).map(provinceTile))
</script>

<template>
  <section class="chart-panel">
    <header class="chart-head">
      <div>
        <h3>省份分布</h3>
        <p class="chart-note">
          按省份字段的分类排列，32 个省级行政区以及香港、澳门、全国、国央企都在其中；大数字是停更网站数，色条是正常、关注、停更的占比。点击卡片筛选下方列表
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
    <ul
      class="province-grid"
      aria-label="省份分布"
    >
      <li
        v-for="tile in tiles"
        :key="tile.item.name"
      >
        <button
          type="button"
          class="province-tile"
          :class="{ selected: provinceSelected(tile.item, selected), empty: !tile.item.sites }"
          :disabled="!tile.item.sites"
          :aria-pressed="provinceSelected(tile.item, selected)"
          :title="tile.hint"
          @click="emit('pick', tile.item.raw_names)"
        >
          <span class="tile-name">{{ tile.item.name }}</span>
          <strong class="tile-stale">{{ tile.item.stale.toLocaleString() }}</strong>
          <span class="tile-caption">{{ tile.caption }}</span>
          <span
            class="tile-bar"
            aria-hidden="true"
          >
            <span
              class="seg seg-normal"
              :style="{ width: `${tile.shares.normal}%` }"
            />
            <span
              class="seg seg-watch"
              :style="{ width: `${tile.shares.watch}%` }"
            />
            <span
              class="seg seg-stale"
              :style="{ width: `${tile.shares.stale}%` }"
            />
          </span>
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.chart-tools { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.province-legend { display: flex; gap: 12px; margin: 0; padding: 0; list-style: none; font-size: 12px; color: var(--zt-ink-500); }
.province-legend li { display: flex; align-items: center; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 2px; }
.province-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: var(--zt-space-2);
  margin: 0; padding: 0; list-style: none;
}
.province-tile {
  display: flex; flex-direction: column; gap: 2px; width: 100%; padding: 8px 10px;
  border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel);
  font: inherit; text-align: left; color: var(--zt-ink-700); cursor: pointer;
  transition: background-color 150ms ease-out, border-color 150ms ease-out;
}
.province-tile:hover:not(:disabled) { background: var(--zt-soft); }
.province-tile:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.province-tile.selected { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-5); }
.province-tile.empty { cursor: default; color: var(--zt-ink-500); background: var(--zt-soft); }
.tile-name { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile-stale { font-size: 20px; line-height: 1.3; color: var(--chart-stale); font-variant-numeric: tabular-nums; }
.empty .tile-stale { color: var(--zt-ink-500); }
.tile-caption { font-size: 12px; color: var(--zt-ink-500); font-variant-numeric: tabular-nums; white-space: nowrap; }
.tile-bar { display: flex; height: 4px; margin-top: 4px; border-radius: 2px; overflow: hidden; background: var(--zt-border); }
.seg-normal { background: var(--chart-normal); }
.seg-watch { background: var(--chart-watch); }
.seg-stale { background: var(--chart-stale); }
</style>
