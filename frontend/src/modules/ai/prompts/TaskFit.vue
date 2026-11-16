<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheckFilled, CircleCloseFilled, RemoveFilled, WarningFilled } from '@element-plus/icons-vue'

import { fitLevel, type TaskFitResult } from './taskFit'

/**
 * 政策类模板放进五个打标任务的检查（按草稿）：用得上的排最前，必须改的标红，可能不理想的标黄；
 * 模板本来不是给那个任务用的（一个必需输出字段都没有）并排收在底部显示灰色「不适用」，原因放悬停提示。
 */
const props = defineProps<{ results: TaskFitResult[] }>()
const ICONS = { ok: CircleCheckFilled, warn: WarningFilled, error: CircleCloseFilled, skip: RemoveFilled }
const LABELS = { ok: '可以用', warn: '可以用，有提醒', error: '不能用，要改', skip: '不适用' }
const sorted = computed(() => [...props.results].sort((a, b) => Number(a.skip) - Number(b.skip)))

function lines(item: TaskFitResult): string[] {
  if (item.skip) return []
  return [...item.check.errors, ...item.check.warnings]
}

function skipHint(item: TaskFitResult): string | undefined {
  return item.skip ? `输出字段里没有${item.required.join('、')}，不是给这个任务用的` : undefined
}
</script>

<template>
  <p
    v-if="!results.length"
    class="task-fit__empty"
  >
    写好提示词和输出字段后，这里检查它能不能用于政策类型判断、政策解读、政策市场机会等定时任务。
  </p>
  <ul
    v-else
    class="task-fit"
    aria-label="定时任务适配"
  >
    <li
      v-for="item in sorted"
      :key="item.code"
      :class="`is-${fitLevel(item)}`"
      :title="skipHint(item)"
    >
      <el-icon class="task-fit__icon">
        <component :is="ICONS[fitLevel(item)]" />
      </el-icon>
      <div class="task-fit__body">
        <span class="task-fit__name">{{ item.name }}</span>
        <span class="task-fit__level">{{ LABELS[fitLevel(item)] }}</span>
        <p
          v-for="text in lines(item)"
          :key="text"
        >
          {{ text }}
        </p>
      </div>
    </li>
  </ul>
</template>

<style scoped>
.task-fit { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; margin: 0; padding: 0; list-style: none; }
.task-fit li { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; line-height: 1.5; }
.task-fit li.is-skip { opacity: 0.72; }
.task-fit__icon { flex: none; font-size: 14px; }
.is-skip .task-fit__icon { font-size: 12px; color: var(--zt-muted-mark); }
.is-ok .task-fit__icon { color: var(--zt-success); }
.is-warn .task-fit__icon { color: var(--zt-warning); }
.is-error .task-fit__icon { color: var(--zt-danger-text); }
.task-fit__body { display: inline-flex; align-items: center; gap: 5px; flex-wrap: wrap; min-width: 0; }
.task-fit__name { color: var(--zt-ink-900); font-weight: 600; }
.is-skip .task-fit__name { color: var(--zt-ink-500); font-weight: 400; }
.task-fit__level { color: var(--zt-ink-500); }
.is-skip .task-fit__level { color: var(--zt-ink-400); }
.is-error .task-fit__level { color: var(--zt-danger-text); }
.task-fit p { flex-basis: 100%; margin: 1px 0 0; color: var(--zt-ink-700); font-size: 12px; overflow-wrap: anywhere; }
.task-fit__empty { margin: 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.5; }
</style>
