<script setup lang="ts">
import { computed } from 'vue'
import type { RunRow } from '@/api/ai'
import { ROW_STATUS_TEXT, fieldCell } from './sampleView'

/** 样本试跑主面板里的宽表预览：直接按当前模板动态列渲染，点任意行打开详尽对照或单条试发。 */
const props = defineProps<{
  columns: string[]
  fields: string[]
  items: RunRow[]
  canRun: boolean
  activeRow?: number
}>()
const emit = defineEmits<{ pick: [row: number]; trial: [row: number] }>()
const titleCol = computed(() => props.columns[0] ?? '')
</script>

<template>
  <div class="matrix-wrap">
    <table class="matrix">
      <thead>
        <tr>
          <th class="is-no">
            #
          </th>
          <th
            v-if="titleCol"
            class="is-title"
          >
            {{ titleCol }}
          </th>
          <th
            v-for="field in fields"
            :key="field"
            class="is-ai"
          >
            {{ field }}
          </th>
          <th
            v-if="!fields.length"
            class="is-ai"
          >
            模型回答
          </th>
          <th class="is-act">
            操作
          </th>
        </tr>
      </thead>
      <tbody>
        <!-- 整行可点只给鼠标；键盘走行号按钮。行本身不做 role="button"：里面还有「试发」按钮，
             嵌套按钮读屏说不清，行上的 Enter 处理还会吞掉「试发」的回车（打开的是详情，不是试发）。 -->
        <tr
          v-for="row in items"
          :key="row.row"
          :class="[`is-${row.status}`, { 'is-changed': row.change, 'is-active-row': activeRow === row.row }]"
          @click="emit('pick', row.row)"
        >
          <td class="is-no">
            <button
              type="button"
              class="matrix__no"
              :aria-label="`查看第 ${row.row} 行详情`"
              @click.stop="emit('pick', row.row)"
            >
              {{ row.row }}
            </button>
          </td>
          <td
            v-if="titleCol"
            class="is-title"
            :title="row.inputs[titleCol]"
          >
            {{ row.inputs[titleCol] || '—' }}
          </td>
          <td
            v-for="field in fields"
            :key="field"
            class="is-field"
            :title="fieldCell(row, field).now"
          >
            <span :class="{ 'is-empty': !fieldCell(row, field).now }">{{ fieldCell(row, field).now || '—' }}</span>
            <s
              v-if="fieldCell(row, field).before !== null"
              class="matrix__was"
            >{{ fieldCell(row, field).before || '空' }}</s>
          </td>
          <td
            v-if="!fields.length"
            class="is-field"
            :title="row.answer"
          >
            {{ row.answer || '—' }}
          </td>
          <td
            class="is-act"
            @click.stop
          >
            <span
              class="matrix__status"
              :class="`is-${row.status}`"
            >{{ ROW_STATUS_TEXT[row.status] }}</span>
            <button
              v-if="canRun"
              type="button"
              class="matrix__btn"
              @click="emit('trial', row.row)"
            >
              试发
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.matrix-wrap { flex: none; width: 100%; max-width: 100%; min-width: 0; overflow: auto; max-height: 360px; border: 1px solid var(--zt-border); border-radius: 10px; background: var(--zt-panel); }
.matrix { width: max-content; min-width: 100%; border-collapse: collapse; font-size: 12.5px; text-align: left; font-variant-numeric: tabular-nums; }
.matrix th { position: sticky; top: 0; z-index: 2; padding: 8px 10px; background: var(--zt-table-head); border-bottom: 1px solid var(--zt-border); color: var(--zt-ink-700); font-weight: 600; white-space: nowrap; }
.matrix th.is-ai { background: var(--zt-ai-soft); color: var(--zt-ai-text); }
.matrix td { padding: 8px 10px; border-bottom: 1px solid var(--zt-divider); color: var(--zt-ink-900); vertical-align: top; max-width: 240px; }
.matrix tr { cursor: pointer; }
.matrix tr:hover td { background: var(--zt-row-hover); }
.matrix tr.is-active-row td { background: var(--el-color-primary-light-9); }
.matrix tr.is-failed td { background: var(--zt-danger-soft); }
.matrix tr.is-format td { background: var(--zt-warning-soft); }
.matrix .is-no { position: sticky; left: 0; z-index: 1; width: 40px; background: inherit; }
.matrix th.is-no { z-index: 3; background: var(--zt-table-head); }
.matrix .is-title { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.matrix .is-field > span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.matrix .is-empty { color: var(--zt-ink-400); }
.matrix__was { display: block; overflow: hidden; color: var(--zt-ink-400); font-size: 11.5px; text-overflow: ellipsis; white-space: nowrap; }
.matrix__no { display: inline-grid; place-items: center; min-width: 22px; height: 22px; padding: 0 4px; border: 0; border-radius: 6px; background: var(--zt-soft); color: var(--zt-ink-700); font: inherit; font-weight: 600; cursor: pointer; }
.matrix__no:focus-visible, .matrix__btn:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.is-changed .matrix__no { background: var(--el-color-primary-light-9); color: var(--zt-blue-700); }
.matrix .is-act { white-space: nowrap; text-align: right; }
.matrix__status { font-size: 11.5px; margin-right: 6px; }
.matrix__status.is-done { color: var(--zt-success-text); }
.matrix__status.is-failed { color: var(--zt-danger-text); }
.matrix__status.is-format { color: var(--zt-warning-text); }
.matrix__btn { padding: 2px 8px; border: 1px solid var(--el-color-primary-light-7); border-radius: 999px; background: var(--el-color-primary-light-9); color: var(--zt-blue-700); font-size: 11.5px; font-weight: 600; cursor: pointer; }
.matrix__btn:hover { background: var(--el-color-primary-light-8); }
</style>
