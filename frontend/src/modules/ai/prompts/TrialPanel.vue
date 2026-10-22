<script setup lang="ts">
import type { AiModel } from '@/api/ai'
import AnswerTranscript from '../shared/AnswerTranscript.vue'
import StreamStatsBar from '../shared/StreamStatsBar.vue'
import type { useAnswerStream } from '../shared/useAnswerStream'

/** 提问配置右栏：试发的回答、用量，以及常驻底部的「试发」按钮（编辑器里 Ctrl/⌘ + Enter 同效）。 */
defineProps<{ answer: ReturnType<typeof useAnswerStream>; model: AiModel | undefined; canRun: boolean; hasExcel: boolean }>()
const emit = defineEmits<{ run: [] }>()
const thinking = defineModel<boolean>('thinking', { default: false })
</script>

<template>
  <aside class="ai-panel trial">
    <div class="ai-panel__head">
      <div>
        <h2>试发</h2>
        <p class="ai-panel__hint">
          {{ hasExcel ? '变量取 Excel 第 1 行' : '没有测试数据时变量原样发出' }}
        </p>
      </div>
      <div class="trial__tools">
        <el-switch
          v-if="model?.supports_thinking"
          v-model="thinking"
          size="small"
          active-text="深度思考"
        />
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
    </div>
    <AnswerTranscript
      :messages="answer.messages.value"
      :running="answer.running.value"
      empty="写好提示词后按 Ctrl/⌘ + Enter 试发。&#10;回答会出现在这里，满意了再保存、上线或到「批量提问」逐行运行。"
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
  </aside>
</template>

<style scoped>
.trial { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.trial__tools { display: flex; align-items: center; gap: 8px; }
.trial__tools .el-button { margin: 0; }
.trial__run { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 16px; border-top: 1px solid var(--zt-border); background: #fafbfd; }
.trial__model { min-width: 0; overflow: hidden; color: var(--zt-ink-500); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.trial__run kbd { margin-left: 6px; padding: 0 4px; border-radius: 3px; background: rgb(255 255 255 / 22%); font: 11px/16px var(--zt-font); }
</style>
