<script setup lang="ts">
import { computed } from 'vue'

import type { CrawlerProvince } from '@/api/crawlerMonitoring'
import { provinceSelected, provinceTile } from './charts'

const props = defineProps<{ rows: CrawlerProvince[]; selected: string[] }>()
const emit = defineEmits<{ pick: [rawNames: string[]] }>()

const tiles = computed(() => props.rows.map(provinceTile))
</script>

<template>
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
</template>

<style scoped>
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
