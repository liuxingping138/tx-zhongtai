<script setup lang="ts">
import { computed } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'

import type { CandidateItem } from '@/api/scenarioCandidates'
import { KIND_NEW, suggest, type DecisionMode } from './candidates'

/**
 * 一个新增场景的决定（2026-11-03 用户挑的样式 C）：只露出系统建议的那个，写全「采纳为新场景」「合并到它」，
 * 其余（另选一个合并、改个名再采纳、驳回）收进「其他」；没有建议时只有一个「决定」。
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
const MENU: Record<DecisionMode, string> = { adopt: '采纳为新场景', merge: '合并到已有场景…', rename: '改个名再采纳', reject: '驳回' }

const suggested = computed(() => suggest(props.candidate))
const main = computed(() => {
  const mode = suggested.value
  if (!mode) return null
  return {
    mode,
    label: mode === 'adopt' ? '采纳为新场景' : '合并到它',
    title: props.canWriteCodebook ? (mode === 'adopt' ? '写进行业场景码表，作为新场景' : '合并到这一行写着的那个已有场景') : NO_CODEBOOK,
  }
})
const others = computed(() => {
  const isNew = props.candidate.kind === KIND_NEW
  return (['adopt', 'merge', 'rename', 'reject'] as const)
    .filter(mode => mode !== suggested.value && (mode !== 'rename' || isNew))
    .map(mode => ({ mode, label: MENU[mode], disabled: mode !== 'reject' && !props.canWriteCodebook }))
})
</script>

<template>
  <div
    class="decide"
    role="group"
    :aria-label="`决定「${candidate.name}」`"
  >
    <el-button
      v-if="main"
      type="primary"
      class="decide__main"
      :disabled="!canWriteCodebook || Boolean(busy)"
      :loading="busy === main.mode"
      :title="main.title"
      @click="emit('open', main.mode)"
    >
      <template v-if="busy !== main.mode">
        <svg
          v-if="main.mode === 'adopt'"
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
      {{ main.label }}
    </el-button>
    <el-dropdown
      trigger="click"
      :disabled="Boolean(busy)"
      @command="(mode: DecisionMode) => emit('open', mode)"
    >
      <el-button
        class="decide__more"
        :loading="Boolean(busy) && busy !== main?.mode"
      >
        {{ main ? '其他' : '决定' }}<el-icon class="el-icon--right">
          <ArrowDown />
        </el-icon>
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="item in others"
            :key="item.mode"
            :command="item.mode"
            :disabled="item.disabled"
          >
            {{ item.label }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<style scoped>
.decide {
  display: inline-flex;
  flex-wrap: nowrap;
  gap: var(--zt-space-2);
  align-items: center;
}

.decide .el-button {
  height: 30px;
  margin: 0;
  font-size: 13px;
}

/* 主按钮一样宽：「采纳为新场景」「合并到它」上下几行对得齐 */
.decide__main {
  min-width: 112px;
  padding: 0 14px;
  font-weight: 500;
}

.decide__more {
  padding: 0 10px;
  color: var(--zt-ink-700);
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
