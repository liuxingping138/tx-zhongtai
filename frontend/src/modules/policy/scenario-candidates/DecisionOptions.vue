<script setup lang="ts">
import type { CandidateItem } from '@/api/scenarioCandidates'
import { KIND_NEW, pathText, type DecisionMode, type Suggestion } from './candidates'

/** 审核页的三种处理，并排写清确定后会发生什么；系统建议的那张加框。 */
defineProps<{
  candidate: CandidateItem
  suggestion: Suggestion
  mergeTarget: string[] | null
  canWriteCodebook: boolean
}>()
const emit = defineEmits<{ open: [mode: DecisionMode, target?: string[] | null] }>()
</script>

<template>
  <section
    class="candidate__options"
    aria-label="怎么处理"
  >
    <article :class="['option', { 'option--suggested': suggestion === 'merge' }]">
      <span
        v-if="suggestion === 'merge'"
        class="option__badge"
      >系统建议 · 码表里有高度相似的</span>
      <h2>{{ mergeTarget ? `合并到「${mergeTarget[mergeTarget.length - 1]}」` : '合并到已有场景' }}</h2>
      <p class="option__path">
        {{ mergeTarget ? pathText(mergeTarget) : '在码表里选一个已有场景' }}
      </p>
      <ul>
        <li>{{ candidate.row_count.toLocaleString() }} 行解读改用这个场景，回填它的编码</li>
        <li>这个说法记成它的别名，以后 AI 再写自动归过去</li>
        <li>码表不新增编号</li>
      </ul>
      <el-button
        :type="suggestion === 'merge' ? 'primary' : 'default'"
        :disabled="!canWriteCodebook"
        :title="canWriteCodebook ? '' : '合并要写行业场景码表，需要码表的管理权限'"
        @click="emit('open', 'merge', mergeTarget)"
      >
        {{ suggestion === 'merge' ? '按建议合并…' : '合并…' }}
      </el-button>
    </article>
    <article :class="['option', { 'option--suggested': suggestion === 'adopt' }]">
      <span
        v-if="suggestion === 'adopt'"
        class="option__badge"
      >系统建议</span>
      <h2>采纳为新场景</h2>
      <p class="option__path">
        {{ candidate.kind === KIND_NEW ? `${candidate.parent || '一级场景'}下新增「${candidate.name}」` : `挂到 ${candidate.industry}` }}
      </p>
      <ul>
        <li>写进行业场景码表，按现有规则顺延编号，标「AI 新增」</li>
        <li>{{ candidate.row_count.toLocaleString() }} 行解读回填编码</li>
        <li>以后 AI 再写这个说法直接回填，不再进待审</li>
      </ul>
      <el-button
        :type="suggestion === 'adopt' ? 'primary' : 'default'"
        :disabled="!canWriteCodebook"
        :title="canWriteCodebook ? '' : '采纳要写行业场景码表，需要码表的管理权限'"
        @click="emit('open', 'adopt')"
      >
        采纳…
      </el-button>
    </article>
    <article class="option">
      <h2>驳回</h2>
      <p class="option__path">
        不是一个该进码表的场景
      </p>
      <ul>
        <li>{{ candidate.row_count.toLocaleString() }} 行解读留着，场景状态标「已驳回」</li>
        <li>以后 AI 再写这个说法自动驳回</li>
        <li>个别政策该归到别的场景：在来源政策里逐条改</li>
      </ul>
      <el-button @click="emit('open', 'reject')">
        驳回…
      </el-button>
    </article>
  </section>
</template>

<style scoped>
.candidate__options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--zt-space-4);
}

.option {
  display: flex;
  flex-direction: column;
  gap: var(--zt-space-2);
  padding: var(--zt-space-4) var(--zt-space-6);
  border: 1px solid var(--zt-border);
  border-radius: var(--zt-radius);
  background: var(--zt-panel);
}

.option--suggested {
  border-color: var(--el-color-primary);
  box-shadow: inset 0 0 0 1px var(--el-color-primary);
}

.option__badge {
  align-self: flex-start;
  padding: 0 8px;
  border-radius: 4px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 12px;
  line-height: 22px;
}

.option h2 {
  margin: 0;
  font-size: 16px;
}

.option__path {
  margin: 0;
  color: var(--zt-ink-500);
  font-size: 13px;
}

.option ul {
  flex: 1;
  margin: 0;
  padding-left: 18px;
  color: var(--zt-ink-700);
  font-size: 13px;
  line-height: 20px;
}

.option .el-button {
  align-self: flex-start;
}
</style>
