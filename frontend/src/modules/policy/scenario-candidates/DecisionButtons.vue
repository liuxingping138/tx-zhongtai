<script setup lang="ts">
import { computed } from 'vue'

import type { CandidateItem } from '@/api/scenarioCandidates'
import { KIND_NEW, suggest, type DecisionMode } from './candidates'

/**
 * 一个新增场景的决定：能做的都摆出来，不收进「其他」（2026-11-03 用户：别硬藏了）。
 * 系统建议的那个排第一、实心主色带图标；其余是描边小按钮，驳回用危险色字。
 * 各自分开、不连成一组（连成一组的四个按钮用户嫌丑）。没有建议时全是描边按钮。
 * 新增场景审核列表每行、解读核对页上场景那一行共用。点了都先开确认框。
 */
const props = defineProps<{
  candidate: CandidateItem
  canWriteCodebook: boolean
  /** 正在取依据、准备开确认框的那一个 */
  busy: DecisionMode | null
}>()
const emit = defineEmits<{ open: [mode: DecisionMode] }>()

const NO_CODEBOOK = '采纳、合并要写行业场景码表，需要码表的管理权限'
// 按钮只写两三个字，完整意思在悬停提示里（2026-11-03 用户：别那么长，知道意思就行）
const LABEL: Record<DecisionMode, string> = { adopt: '采纳', merge: '合并', rename: '改名', reject: '驳回' }
const HINT: Record<DecisionMode, string> = {
  adopt: '采纳为新场景：写进行业场景码表',
  merge: '合并到已有场景：以后这个说法都归到那里',
  rename: '改个名再采纳：换个名称再写进码表',
  reject: '驳回：不进码表，以后 AI 再写这个说法也直接驳回',
}

const suggested = computed(() => suggest(props.candidate))
const actions = computed(() => {
  const isNew = props.candidate.kind === KIND_NEW
  const modes = (['adopt', 'merge', 'rename', 'reject'] as const).filter(mode => mode !== 'rename' || isNew)
  // 建议的那个挪到最前
  const ordered = suggested.value ? [suggested.value, ...modes.filter(mode => mode !== suggested.value)] : [...modes]
  return ordered.map((mode) => {
    const primary = mode === suggested.value
    const locked = mode !== 'reject' && !props.canWriteCodebook
    return {
      mode,
      primary,
      label: LABEL[mode],
      title: locked ? NO_CODEBOOK : primary && mode === 'merge' ? '合并到这一行写着的那个已有场景' : HINT[mode],
      disabled: locked || Boolean(props.busy),
    }
  })
})
</script>

<template>
  <div
    class="decide"
    role="group"
    :aria-label="`决定「${candidate.name}」`"
  >
    <el-button
      v-for="item in actions"
      :key="item.mode"
      :type="item.primary ? 'primary' : undefined"
      :class="['decide__btn', { 'decide__btn--main': item.primary, 'decide__btn--reject': item.mode === 'reject' }]"
      :disabled="item.disabled"
      :loading="busy === item.mode"
      :title="item.title"
      @click="emit('open', item.mode)"
    >
      <template v-if="item.primary && busy !== item.mode">
        <svg
          v-if="item.mode === 'adopt'"
          class="decide__icon"
          viewBox="0 0 12 12"
          aria-hidden="true"
        ><path d="M2.5 6.2l2.3 2.3L9.5 3.8" /></svg>
        <svg
          v-else
          class="decide__icon"
          viewBox="0 0 12 12"
          aria-hidden="true"
        ><path d="M1.5 6h7M6 3l3 3-3 3M10.5 2v8" /></svg>
      </template>
      {{ item.label }}
    </el-button>
  </div>
</template>

<style scoped>
.decide {
  display: inline-flex;
  flex-wrap: nowrap;
  gap: 4px;
  align-items: center;
}

.decide .el-button {
  height: 28px;
  margin: 0;
  padding: 0 9px;
  font-size: 13px;
}

.decide__btn:not(.decide__btn--main) {
  color: var(--zt-ink-700);
}

/* 建议的那个：「采纳」「合并」一样宽，上下几行对得齐 */
.decide .decide__btn--main {
  min-width: 64px;
  padding: 0 10px;
  font-weight: 500;
}

.decide .decide__btn--reject:not(.is-disabled) {
  color: var(--zt-danger-text);
}

.decide .decide__btn--reject:not(.is-disabled):hover {
  border-color: var(--zt-danger-border);
  background: var(--zt-danger-soft);
}

.decide__icon {
  width: 12px;
  height: 12px;
  margin-right: 6px;
  fill: none;
  stroke: currentcolor;
  stroke-width: 1.7;
}
</style>
