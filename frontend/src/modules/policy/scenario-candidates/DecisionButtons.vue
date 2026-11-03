<script setup lang="ts">
import { computed } from 'vue'

import type { CandidateItem } from '@/api/scenarioCandidates'
import { KIND_NEW, suggest, type DecisionMode } from './candidates'

/**
 * 列表每行的四个决定，连成一组、每行位置一样；系统建议的那个填主色。
 * 新关联是码表已有的场景，不能改名，那一格置灰、不挪位置。点了都先开确认框。
 */
const props = defineProps<{
  candidate: CandidateItem
  canWriteCodebook: boolean
  /** 正在取依据、准备开确认框的那一个 */
  busy: DecisionMode | null
}>()
const emit = defineEmits<{ open: [mode: DecisionMode] }>()

const NO_CODEBOOK = '采纳、合并要写行业场景码表，需要码表的管理权限'
const buttons = computed(() => {
  const suggested = suggest(props.candidate)
  const codebook = props.canWriteCodebook ? '' : NO_CODEBOOK
  const isNew = props.candidate.kind === KIND_NEW
  return [
    { mode: 'adopt' as const, label: '采纳', primary: suggested === 'adopt', disabled: !props.canWriteCodebook, title: codebook || '采纳为新场景，写进行业场景码表' },
    { mode: 'merge' as const, label: '合并', primary: suggested === 'merge', disabled: !props.canWriteCodebook, title: codebook || '合并到码表里已有的场景' },
    {
      mode: 'rename' as const,
      label: '改名',
      primary: false,
      disabled: !props.canWriteCodebook || !isNew,
      title: codebook || (isNew ? '改个名再采纳' : '新关联是码表已有的场景，不能改名'),
    },
    { mode: 'reject' as const, label: '驳回', primary: false, disabled: false, title: '驳回这个新增场景' },
  ]
})
</script>

<template>
  <el-button-group
    class="decide"
    role="group"
    :aria-label="`决定「${candidate.name}」`"
  >
    <el-button
      v-for="item in buttons"
      :key="item.mode"
      :type="item.primary ? 'primary' : 'default'"
      :disabled="item.disabled || Boolean(busy)"
      :loading="busy === item.mode"
      :title="item.title"
      @click.stop="emit('open', item.mode)"
    >
      {{ item.label }}
    </el-button>
  </el-button-group>
</template>

<style scoped>
.decide {
  display: inline-flex;
  flex-wrap: nowrap;
}

.decide .el-button {
  height: 28px;
  padding: 0 13px;
  font-size: 13px;
}

.decide .el-button--default:not(.is-disabled) {
  color: var(--zt-ink-900);
}

.decide .el-button--primary {
  font-weight: 500;
}
</style>
