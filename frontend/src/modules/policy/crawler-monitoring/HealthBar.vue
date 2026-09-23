<script setup lang="ts">
import { computed } from 'vue'
import { Check } from '@element-plus/icons-vue'
import type { HealthStatus } from '@/api/crawlerMonitoring'

const props = defineProps<{
  items: { status: HealthStatus; label: string; count: number }[]
  selected?: HealthStatus
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
      <span
        v-for="item in items"
        :key="item.status"
        :class="`seg-${item.status}`"
        :style="{ flexGrow: item.count }"
        :title="`${item.label} ${percent(item.count)}%`"
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
          :class="{ selected: selected === item.status }"
          :aria-pressed="selected === item.status"
          @click="emit('pick', item.status)"
        >
          <span class="legend-name"><span
            class="swatch"
            :class="`seg-${item.status}`"
          />{{ item.label }}</span>
          <span class="legend-count">{{ item.count.toLocaleString() }}</span>
          <span class="legend-pct">{{ percent(item.count) }}%</span>
          <el-icon
            class="selection-mark"
            :class="{ visible: selected === item.status }"
          >
            <Check />
          </el-icon>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.bar { display: flex; height: 8px; overflow: hidden; border-radius: 4px; background: var(--zt-soft); }
.bar > span { flex-basis: 0; }
.seg-normal { background: var(--el-color-success); }
.seg-watch { background: var(--el-color-warning); }
.seg-broken { background: var(--el-color-danger); }
.seg-never { background: var(--zt-ink-500); }
.legend { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 4px; }
.legend-item {
  display: grid; grid-template-columns: minmax(76px, 1fr) auto 52px 16px; align-items: center;
  gap: 8px; width: 100%; min-height: 46px; padding: 8px 10px;
  background: transparent; border: 1px solid transparent; border-radius: var(--zt-radius);
  font: inherit; color: var(--zt-ink-700); text-align: left; cursor: pointer;
}
.legend-item:hover { background: var(--zt-soft); }
.legend-item.selected { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-7); }
.legend-item:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.legend-name { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.swatch { width: 8px; height: 8px; border-radius: 2px; flex: none; }
.legend-count { color: var(--zt-ink-900); font-weight: 600; font-size: 16px; font-variant-numeric: tabular-nums; }
.legend-pct { color: var(--zt-ink-500); text-align: right; font-size: 12px; font-variant-numeric: tabular-nums; }
.selection-mark { visibility: hidden; color: var(--zt-blue-600); }
.selection-mark.visible { visibility: visible; }
</style>
