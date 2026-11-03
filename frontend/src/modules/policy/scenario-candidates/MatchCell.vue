<script setup lang="ts">
import { computed } from 'vue'

import type { CandidateItem } from '@/api/scenarioCandidates'
import { matchOf, splitLeaf } from './candidates'

/**
 * 列表「码表里像它的」：上面是像它的那个场景（末级加粗），下面一个和「新一级」同款的标签写结论，
 * 颜色就是结论：蓝 AI 说该合并、橙 名称很像、灰 名称有点像、绿 码表里没有。往下扫一眼就知道哪些该合并、哪些该采纳。
 */
const props = defineProps<{ candidate: CandidateItem }>()
const match = computed(() => matchOf(props.candidate))
const path = computed(() => splitLeaf(match.value.name))
</script>

<template>
  <div class="match-cell">
    <span
      v-if="match.kind !== 'none'"
      class="match-cell__path"
    ><span
      v-if="path.parent"
      class="match-cell__parent"
    >{{ path.parent }} › </span><strong>{{ path.leaf }}</strong></span>
    <span
      v-else
      class="match-cell__path match-cell__path--none"
    >没有像的</span>
    <span class="match-cell__verdict">
      <span :class="['match-cell__tag', `match-cell__tag--${match.kind}`]">{{ match.kind === 'none' ? '码表里没有' : match.label }}</span>
      <span
        v-if="match.note"
        class="match-cell__note"
      >{{ match.note }}</span>
    </span>
  </div>
</template>

<style scoped>
.match-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  line-height: 20px;
}

.match-cell__path {
  color: var(--zt-ink-900);
}

.match-cell__path strong {
  font-weight: 600;
}

.match-cell__parent,
.match-cell__path--none {
  color: var(--zt-ink-500);
}

.match-cell__verdict {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

/* 和「新增场景级别」的标签同一个样子，只换颜色 */
.match-cell__tag {
  padding: 0 8px;
  border: 1px solid var(--zt-border);
  border-radius: 4px;
  background: var(--zt-soft);
  color: var(--zt-ink-700);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}

.match-cell__tag--ai {
  border-color: var(--el-color-primary-light-7);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.match-cell__tag--high {
  border-color: var(--zt-warning-border);
  background: var(--zt-warning-soft);
  color: var(--zt-warning-text);
}

.match-cell__tag--none {
  border-color: var(--zt-success-border);
  background: var(--zt-success-soft);
  color: var(--zt-success-text);
}

.match-cell__note {
  color: var(--zt-ink-500);
  font-size: 12px;
}
</style>
