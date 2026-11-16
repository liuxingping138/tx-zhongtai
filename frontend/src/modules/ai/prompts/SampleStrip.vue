<script setup lang="ts">
import { computed } from 'vue'

import type { RunRow } from '@/api/ai'
import { ROW_STATUS_TEXT, rowCounts } from './sampleView'

/**
 * 样本试跑一格一行：成功是浅绿，调用失败是深红实心，格式不对是琥珀斜纹，和上次不同的格子下面有一道蓝线。
 * 每格写着行号，下面的图例写着每种几行，不只靠颜色认。点一格看这一行。
 */
const props = defineProps<{ rows: RunRow[]; compared: boolean; activeRow?: number }>()
const emit = defineEmits<{ pick: [row: number] }>()
const counts = computed(() => rowCounts(props.rows))

function label(row: RunRow): string {
  return `第 ${row.row} 行 ${ROW_STATUS_TEXT[row.status]}${row.change ? '，和上次不同' : ''}`
}
</script>

<template>
  <div class="strip">
    <ol
      class="strip__cells"
      aria-label="逐行结果，点一格看这一行"
    >
      <li
        v-for="row in rows"
        :key="row.row"
      >
        <button
          type="button"
          class="strip__cell"
          :class="[`is-${row.status}`, { 'is-changed': row.change, 'is-active': activeRow === row.row }]"
          :aria-label="label(row)"
          :title="label(row)"
          @click="emit('pick', row.row)"
        >
          {{ row.row }}
        </button>
      </li>
    </ol>
    <div class="strip__legend">
      <span><i class="strip__key is-done" />成功 <b>{{ counts.done }}</b></span>
      <span v-if="counts.failed"><i class="strip__key is-failed" />调用失败 <b>{{ counts.failed }}</b></span>
      <span v-if="counts.format"><i class="strip__key is-format" />格式不对 <b>{{ counts.format }}</b></span>
      <span v-if="compared"><i class="strip__key is-changed" />和上次不同 <b>{{ counts.changed }}</b></span>
    </div>
  </div>
</template>

<style scoped>
.strip__cells { display: grid; grid-template-columns: repeat(10, minmax(0, 1fr)); gap: 9px 4px; margin: 0; padding: 0; list-style: none; }
.strip__cell { position: relative; display: grid; place-items: center; width: 100%; height: 34px; padding: 0; border: 1px solid var(--zt-success-border); border-radius: 4px; background: var(--zt-success-soft); color: var(--zt-success-text); font: 600 12px/1 var(--zt-font); font-variant-numeric: tabular-nums; cursor: pointer; }
.strip__cell:hover { filter: brightness(0.97); }
.strip__cell:focus-visible { outline: 2px solid var(--zt-blue-600); outline-offset: 2px; }
.strip__cell.is-active { outline: 2px solid var(--zt-blue-600); outline-offset: 1px; box-shadow: 0 2px 6px var(--zt-focus-ring); }
.strip__cell.is-failed { border-color: var(--zt-danger-text); background: var(--zt-danger-text); color: var(--el-color-white); }
.strip__cell.is-format, .strip__key.is-format { border-color: var(--zt-warning); background: repeating-linear-gradient(135deg, var(--zt-warning-soft) 0 5px, var(--zt-warning-border) 5px 10px); color: var(--zt-warning-text); }
.strip__cell.is-pending { border-style: dashed; border-color: var(--zt-border-strong); background: var(--zt-panel); color: var(--zt-ink-400); }
.strip__cell.is-changed::after { content: ""; position: absolute; left: 5px; right: 5px; bottom: -6px; height: 3px; border-radius: 2px; background: var(--zt-blue-600); }
.strip__legend { display: flex; flex-wrap: wrap; gap: 6px 12px; margin-top: 14px; color: var(--zt-ink-700); font-size: 12px; }
.strip__legend span { display: inline-flex; align-items: center; gap: 6px; }
.strip__legend b { color: var(--zt-ink-900); font-weight: 600; font-variant-numeric: tabular-nums; }
.strip__key { width: 12px; height: 12px; border: 1px solid var(--zt-success-border); border-radius: 2px; background: var(--zt-success-soft); }
.strip__key.is-failed { border-color: var(--zt-danger-text); background: var(--zt-danger-text); }
.strip__key.is-changed { height: 3px; border: 0; background: var(--zt-blue-600); }
@media (prefers-reduced-motion: reduce) { .strip__cell { transition: none; } }
</style>
