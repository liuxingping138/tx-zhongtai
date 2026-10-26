<script setup lang="ts">
import type { AiModel } from '@/api/ai'
import AnswerTranscript from '../shared/AnswerTranscript.vue'
import StreamStatsBar from '../shared/StreamStatsBar.vue'
import type { useAnswerStream } from '../shared/useAnswerStream'

/** 试发一条：变量换成测试样本第 1 行，流式看回答。编辑器里 Ctrl/⌘ + Enter 同效。 */
defineProps<{ answer: ReturnType<typeof useAnswerStream>; model: AiModel | undefined; canRun: boolean; hasExcel: boolean }>()
const emit = defineEmits<{ run: [] }>()
</script>

<template>
  <div class="trial">
    <div class="trial__bar">
      <span>{{ hasExcel ? '变量取测试样本第 1 行' : '没有测试样本，变量原样发出' }}</span>
      <el-button
        v-if="answer.running.value"
        size="small"
        @click="answer.stop"
      >
        停止
      </el-button>
      <el-button
        v-else
        size="small"
        text
        :disabled="!answer.messages.value.length"
        @click="answer.clear"
      >
        清空
      </el-button>
    </div>
    <AnswerTranscript
      :messages="answer.messages.value"
      :running="answer.running.value"
      empty="写好提示词按 Ctrl/⌘ + Enter 试发一条，回答出现在这里。&#10;整批效果用「样本试跑」看。"
    />
    <StreamStatsBar
      :stats="answer.stats"
      :cost="answer.cost.value"
    />
    <footer class="trial__run">
      <span class="trial__model">{{ model ? model.name : '没有可用的模型' }}</span>
      <el-button
        v-if="canRun"
        type="primary"
        :disabled="answer.running.value || !model?.available"
        :loading="answer.running.value"
        @click="emit('run')"
      >
        试发 <kbd>Ctrl ↵</kbd>
      </el-button>
    </footer>
  </div>
</template>

<style scoped>
.trial { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.trial__bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 16px; color: var(--zt-ink-500); font-size: 12px; }
.trial__bar .el-button { margin: 0; }
.trial__run { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 16px; border-top: 1px solid var(--zt-border); background: #fafbfd; }
.trial__model { min-width: 0; overflow: hidden; color: var(--zt-ink-500); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.trial__run kbd { margin-left: 6px; padding: 0 4px; border-radius: 3px; background: rgb(255 255 255 / 22%); font: 11px/16px var(--zt-font); }
</style>
