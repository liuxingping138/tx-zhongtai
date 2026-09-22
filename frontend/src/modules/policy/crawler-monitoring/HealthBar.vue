<script setup lang="ts">
import { computed } from 'vue'

import type { HealthStatus } from '@/api/crawlerMonitoring'

const props = defineProps<{
  items: { status: HealthStatus; label: string; count: number }[]
}>()

const emit = defineEmits<{ pick: [status: HealthStatus] }>()

const total = computed(() => props.items.reduce((sum, item) => sum + item.count, 0))

function percent(count: number): number {
  return total.value === 0 ? 0 : Math.round((count / total.value) * 1000) / 10
}
</script>

<template>
  <div class="health-bar">
    <div
      class="bar"
      role="img"
      :aria-label="items.map((item) => `${item.label} ${item.count} 个`).join('，')"
    >
      <button
        v-for="item in items"
        v-show="item.count > 0"
        :key="item.status"
        type="button"
        class="segment"
        :class="`seg-${item.status}`"
        :style="{ width: `${percent(item.count)}%` }"
        :title="`${item.label}：${item.count} 个（${percent(item.count)}%）`"
        @click="emit('pick', item.status)"
      />
    </div>
    <ul class="legend">
      <li
        v-for="item in items"
        :key="item.status"
      >
        <button
          type="button"
          class="legend-item"
          @click="emit('pick', item.status)"
        >
          <span
            class="swatch"
            :class="`seg-${item.status}`"
          />
          <span class="legend-label">{{ item.label }}</span>
          <span class="legend-count">{{ item.count.toLocaleString() }}</span>
          <span class="legend-pct">{{ percent(item.count) }}%</span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  height: 18px;
  border-radius: var(--zt-radius);
  overflow: hidden;
  background: var(--zt-soft);
  border: 1px solid var(--zt-border);
}

.segment {
  border: none;
  padding: 0;
  cursor: pointer;
  transition: opacity 160ms ease;
}

.segment:hover,
.legend-item:hover {
  opacity: 0.82;
}

.seg-normal {
  background: #3f8f5e;
}

.seg-watch {
  background: #c99a2e;
}

.seg-broken {
  background: #c45656;
}

.seg-never {
  background: var(--zt-ink-500);
}

.legend {
  list-style: none;
  margin: var(--zt-space-3) 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-2) var(--zt-space-6);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: var(--zt-space-2);
  background: none;
  border: none;
  padding: 2px 0;
  cursor: pointer;
  font: inherit;
  color: var(--zt-ink-700);
}

.swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  display: inline-block;
}

.legend-count {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--zt-ink-900);
}

.legend-pct {
  color: var(--zt-ink-500);
  font-size: 12px;
}
</style>
