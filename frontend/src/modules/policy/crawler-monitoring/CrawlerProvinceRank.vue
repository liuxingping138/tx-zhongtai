<script setup lang="ts">
import { computed } from 'vue'

import type { CrawlerProvince } from '@/api/crawlerMonitoring'
import { provinceRanks, provinceSelected } from './provinceView'

const props = defineProps<{ rows: CrawlerProvince[]; selected: string[] }>()
const emit = defineEmits<{ pick: [rawNames: string[]] }>()

const ranked = computed(() => provinceRanks(props.rows))
const mid = computed(() => Math.ceil(ranked.value.length / 2))
const columns = computed(() => [ranked.value.slice(0, mid.value), ranked.value.slice(mid.value)])
const hasSelection = computed(() => ranked.value.some(row => provinceSelected(row.item, props.selected)))

function isSelected(item: CrawlerProvince): boolean {
  return provinceSelected(item, props.selected)
}
</script>

<template>
  <div class="rank-grid">
    <ul
      v-for="(col, colIndex) in columns"
      :key="colIndex"
      class="rank-col"
      :aria-label="`省份分布排行第 ${colIndex + 1} 列`"
    >
      <li
        v-for="row in col"
        :key="row.item.name"
      >
        <button
          type="button"
          class="rank-row"
          :class="{
            selected: isSelected(row.item),
            dimmed: hasSelection && !isSelected(row.item),
            empty: !row.item.sites,
          }"
          :disabled="!row.item.sites"
          :aria-pressed="isSelected(row.item)"
          :title="row.hint"
          @click="emit('pick', row.item.raw_names)"
        >
          <span class="rank-num">{{ row.rank }}</span>
          <span class="rank-name">{{ row.shortName }}</span>
          <span
            class="rank-track"
            aria-hidden="true"
          >
            <span
              class="seg seg-ok"
              :style="{ width: `${row.okWidth}%` }"
            />
            <span
              class="seg seg-stale"
              :style="{ width: `${row.staleWidth}%` }"
            />
          </span>
          <span class="rank-meta">
            <strong class="rank-total">{{ row.item.sites.toLocaleString() }}</strong>
            <span
              v-if="row.item.stale"
              class="rank-stale"
              :class="{ high: row.staleRate >= 40 }"
            >停 {{ row.item.stale }}</span>
            <span
              v-else
              class="rank-stale-spacer"
              aria-hidden="true"
            />
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.rank-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--zt-space-2) var(--zt-space-6);
}
.rank-col {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.rank-row {
  display: grid;
  grid-template-columns: 22px 54px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 6px 10px;
  border: 1px solid transparent;
  border-radius: var(--zt-radius);
  background: none;
  font: inherit;
  color: var(--zt-ink-900);
  text-align: left;
  cursor: pointer;
  transition: background-color 140ms ease-out, border-color 140ms ease-out, opacity 160ms ease-out;
}
.rank-row:hover:not(:disabled) {
  background: var(--zt-surface-subtle);
}
.rank-row:focus-visible {
  outline: 2px solid var(--zt-blue-600);
  outline-offset: 2px;
}
.rank-row.selected {
  background: var(--el-color-primary-light-9);
  border-color: var(--zt-blue-600);
}
.rank-row.dimmed {
  opacity: 0.42;
}
.rank-row.empty {
  cursor: default;
  color: var(--zt-ink-400);
}
.rank-num {
  font-size: 12px;
  color: var(--zt-ink-400);
  font-variant-numeric: tabular-nums;
}
.rank-name {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rank-track {
  display: flex;
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--zt-divider);
}
.seg {
  height: 100%;
  transition: width 200ms ease-out;
}
.seg-ok {
  background: var(--zt-blue-600);
}
.seg-stale {
  background: var(--chart-stale);
}
.rank-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  min-width: 82px;
  font-variant-numeric: tabular-nums;
}
.rank-total {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--zt-ink-900);
}
.empty .rank-total {
  color: var(--zt-ink-400);
  font-weight: 400;
}
.rank-stale {
  min-width: 42px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--zt-surface-subtle);
  color: var(--zt-ink-500);
  font-size: 12px;
  text-align: center;
}
.rank-stale.high {
  background: var(--zt-danger-soft);
  color: var(--zt-danger-text);
}
.rank-stale-spacer {
  min-width: 42px;
}
@media (max-width: 900px) {
  .rank-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
