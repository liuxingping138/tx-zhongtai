<script setup lang="ts">
import { Check } from '@element-plus/icons-vue'

import type { FlowStep, StepKey } from './templateStatus'

/** 编辑页顶部的三步：写提示词 → 样本试跑 → 上线。每步写清现在的状态，「下一步」那一格高亮并给出按钮。 */
withDefaults(defineProps<{ steps: FlowStep[]; actions: Partial<Record<StepKey, string>>; primary?: boolean }>(), { primary: true })
const emit = defineEmits<{ step: [key: StepKey] }>()
</script>

<template>
  <ol
    class="flow"
    aria-label="模板进度"
  >
    <li
      v-for="(step, index) in steps"
      :key="step.key"
      class="flow__step"
      :class="`is-${step.tone}`"
      :aria-current="step.tone === 'current' ? 'step' : undefined"
    >
      <span
        class="flow__mark"
        aria-hidden="true"
      >
        <el-icon v-if="step.tone === 'done'"><Check /></el-icon>
        <template v-else-if="step.tone === 'warn'">!</template>
        <template v-else>{{ index + 1 }}</template>
      </span>
      <div class="flow__text">
        <strong>{{ step.title }}</strong>
        <span :title="step.text">{{ step.text }}</span>
      </div>
      <el-button
        v-if="actions[step.key]"
        size="small"
        :type="step.tone === 'current' && primary ? 'primary' : undefined"
        :plain="step.tone !== 'current' || !primary"
        @click="emit('step', step.key)"
      >
        {{ actions[step.key] }}
      </el-button>
    </li>
  </ol>
</template>

<style scoped>
.flow {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 0; padding: 0; list-style: none;
  border-top: 1px solid var(--zt-border); background: var(--zt-surface-subtle);
}
.flow__step {
  position: relative; display: flex; align-items: center; gap: 10px;
  min-width: 0; padding: 9px 18px; transition: background-color 0.15s ease;
}
.flow__step + .flow__step { border-left: 1px solid var(--zt-border); }
.flow__step.is-current { background: var(--el-color-primary-light-9); }
.flow__step.is-current::before {
  content: ""; position: absolute; left: 0; right: 0; top: -1px;
  height: 2px; background: var(--zt-blue-600);
}
.flow__mark {
  display: inline-grid; flex: none; place-items: center;
  width: 22px; height: 22px; border: 1px solid var(--zt-border-strong);
  border-radius: 50%; background: var(--zt-panel); color: var(--zt-ink-500);
  font: 600 11px/1 var(--zt-font); font-variant-numeric: tabular-nums;
}
.is-done .flow__mark { border-color: var(--zt-success-border); background: var(--zt-success-soft); color: var(--zt-success-text); }
.is-warn .flow__mark { border-color: var(--zt-warning-border); background: var(--zt-warning-soft); color: var(--zt-warning-text); }
.is-current .flow__mark {
  border-color: var(--zt-blue-600); background: var(--zt-blue-600);
  color: var(--el-color-white); box-shadow: 0 0 0 3px var(--zt-focus-ring);
}
.flow__text { display: flex; flex: 1; flex-direction: column; min-width: 0; line-height: 1.4; }
.flow__text strong { color: var(--zt-ink-900); font-size: 13px; font-weight: 600; }
.is-todo .flow__text strong { color: var(--zt-ink-500); }
.flow__text span { overflow: hidden; color: var(--zt-ink-500); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.is-warn .flow__text span { color: var(--zt-warning-text); }
.flow__step .el-button { flex: none; margin: 0; }
</style>
