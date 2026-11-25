<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheckFilled, CircleCloseFilled, RemoveFilled, WarningFilled } from '@element-plus/icons-vue'

import { fitLevel, type TaskFitResult } from './taskFit'

/**
 * 政策类模板放进五个打标任务的检查（按草稿）：用得上的排最前，必须改的标红，可能不理想的标黄；
 * 非目标任务显示克制「不适用」并给出缺少的必需输出字段说明。
 */
const props = defineProps<{ results: TaskFitResult[] }>()
const ICONS = { ok: CircleCheckFilled, warn: WarningFilled, error: CircleCloseFilled, skip: RemoveFilled }
const LABELS = { ok: '可用', warn: '可用 · 有提醒', error: '需修改', skip: '不适用' }
const sorted = computed(() => [...props.results].sort((a, b) => Number(a.skip) - Number(b.skip)))

function detailText(item: TaskFitResult): string {
  if (item.skip) return `输出字段未包含「${item.required.join('、')}」，非该任务目标模板`
  const issues = [...item.check.errors, ...item.check.warnings]
  return issues.length ? issues.join('；') : '输入变量与必需输出字段完全匹配，上线后可在任务调度中直接选用'
}
</script>

<template>
  <p
    v-if="!results.length"
    class="task-fit__empty"
  >
    编写提示词与输出字段后，自动核验能否接入政策类型判断、政策解读、政策市场机会等 5 个定时调度任务。
  </p>
  <ul
    v-else
    class="task-fit"
    aria-label="定时任务适配"
  >
    <li
      v-for="item in sorted"
      :key="item.code"
      class="task-fit__item"
      :class="`is-${fitLevel(item)}`"
    >
      <el-icon class="task-fit__icon">
        <component :is="ICONS[fitLevel(item)]" />
      </el-icon>
      <span class="task-fit__name">{{ item.name }}</span>
      <span class="task-fit__badge">{{ LABELS[fitLevel(item)] }}</span>
      <span class="task-fit__msg">{{ detailText(item) }}</span>
    </li>
  </ul>
</template>

<style scoped>
.task-fit { display: grid; gap: 5px; margin: 0; padding: 0; list-style: none; }
.task-fit__item {
  display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px 8px; padding: 5px 10px;
  border: 1px solid var(--zt-divider); border-radius: 6px; background: var(--zt-surface-subtle);
  font-size: 12px; line-height: 1.5;
}
.task-fit__item.is-skip { opacity: 0.68; }
.task-fit__item.is-warn { border-color: var(--zt-warning-border); background: var(--zt-warning-soft); }
.task-fit__item.is-error { border-color: var(--zt-danger-border); background: var(--zt-danger-soft); }

.task-fit__icon { flex: none; font-size: 13px; transform: translateY(2px); }
.is-skip .task-fit__icon { color: var(--zt-muted-mark); }
.is-ok .task-fit__icon { color: var(--zt-success); }
.is-warn .task-fit__icon { color: var(--zt-warning); }
.is-error .task-fit__icon { color: var(--zt-danger-text); }

.task-fit__name { flex: none; color: var(--zt-ink-900); font-weight: 600; }
.task-fit__badge { flex: none; color: var(--zt-ink-500); font-weight: 500; }
.is-ok .task-fit__badge { color: var(--zt-success-text); }
.is-warn .task-fit__badge { color: var(--zt-warning-text); }
.is-error .task-fit__badge { color: var(--zt-danger-text); }
.task-fit__msg { flex: 1 1 220px; min-width: 0; color: var(--zt-ink-700); overflow-wrap: anywhere; }
.task-fit__empty { margin: 0; color: var(--zt-ink-500); font-size: 12px; line-height: 1.5; }
</style>
