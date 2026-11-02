<script setup lang="ts">
import { computed } from 'vue'

import type { CandidateItem } from '@/api/scenarioCandidates'
import { AI_NEW, KIND_NEW, type DecisionMode, type Suggestion } from './candidates'

/** 审核页底部「你的决定」：采纳、改个名再采纳、驳回三个按钮；合并在上面的列表里点。会改什么写在确认框里。 */
const props = defineProps<{
  candidate: CandidateItem
  suggestion: Suggestion
  canWriteCodebook: boolean
}>()
const emit = defineEmits<{ open: [mode: DecisionMode] }>()

const NO_CODEBOOK = '采纳、合并要写行业场景码表，需要码表的管理权限'
const hint = computed(() => {
  if (!props.canWriteCodebook) return NO_CODEBOOK
  if (props.suggestion === 'merge') {
    return props.candidate.ai_verdict ? 'AI 建议合并：在上面点「合并到这里」' : '码表里有名称很像的，看看是不是同一个；要合并在上面点「合并到这里」'
  }
  if (props.suggestion === 'adopt') {
    return props.candidate.ai_verdict === AI_NEW ? 'AI 认为码表里没有同样的，建议采纳' : '没有像的，且不止一两条政策这么说，建议采纳'
  }
  return '合并在上面的列表里点；点了哪个，确认框里会写清会改哪些东西'
})
</script>

<template>
  <section
    class="decide"
    aria-label="你的决定"
  >
    <span class="decide__title">你的决定</span>
    <el-button
      type="primary"
      :plain="suggestion !== 'adopt'"
      :disabled="!canWriteCodebook"
      :title="canWriteCodebook ? '' : NO_CODEBOOK"
      @click="emit('open', 'adopt')"
    >
      采纳为新场景
    </el-button>
    <el-button
      v-if="candidate.kind === KIND_NEW"
      :disabled="!canWriteCodebook"
      :title="canWriteCodebook ? '' : NO_CODEBOOK"
      @click="emit('open', 'rename')"
    >
      改个名再采纳
    </el-button>
    <el-button @click="emit('open', 'reject')">
      驳回
    </el-button>
    <span class="decide__hint">{{ hint }}</span>
  </section>
</template>

<style scoped>
.decide {
  display: flex;
  flex-wrap: wrap;
  gap: var(--zt-space-3);
  align-items: center;
  padding: var(--zt-space-4) var(--zt-space-6);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
}

.decide .el-button + .el-button {
  margin-left: 0;
}

.decide__title {
  margin-right: var(--zt-space-2);
  font-size: 15px;
  font-weight: 600;
}

.decide__hint {
  margin-left: auto;
  color: var(--zt-ink-500);
  font-size: 13px;
}
</style>
