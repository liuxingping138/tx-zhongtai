<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { chatModels, type AiModel } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import AnswerTranscript from '../shared/AnswerTranscript.vue'
import ModelPicker from '../shared/ModelPicker.vue'
import StreamStatsBar from '../shared/StreamStatsBar.vue'
import { useAnswerStream } from '../shared/useAnswerStream'
import '../shared/ai.css'

const models = ref<AiModel[]>([])
const modelId = ref('')
const thinking = ref(false)
const input = ref('')
const loadError = ref('')
const { messages, running, responseId, stats, cost, send, stop, clear } = useAnswerStream()
const current = computed(() => models.value.find(item => item.id === modelId.value))
const canSend = computed(() => Boolean(input.value.trim()) && Boolean(current.value?.available) && !running.value)

onMounted(async () => {
  try {
    models.value = await chatModels()
    modelId.value = models.value.find(item => item.available)?.id ?? models.value[0]?.id ?? ''
  } catch (error) {
    loadError.value = errorMessage(error, '模型列表加载失败，请刷新重试')
  }
})
onBeforeUnmount(stop)

/** 换模型等于换了一段上下文：服务端保存的上一轮回答属于原来的模型。 */
function changeModel(): void {
  if (messages.value.length) clear()
}

async function submit(): Promise<void> {
  if (!canSend.value) return
  const text = input.value.trim()
  input.value = ''
  const useThinking = thinking.value && Boolean(current.value?.supports_thinking)
  await send('/ai/stream/chat', {
    message: text,
    model_id: modelId.value,
    thinking: useThinking,
    previous_response_id: responseId.value,
  }, text, useThinking)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void submit()
  }
}
</script>

<template>
  <section class="ai-chat">
    <h1 class="ai-sr-only">
      多轮对话
    </h1>
    <header class="ai-chat__bar">
      <ModelPicker
        v-model="modelId"
        v-model:thinking="thinking"
        :models="models"
        @update:model-value="changeModel"
      />
      <el-button
        :disabled="!messages.length"
        @click="clear"
      >
        清空对话
      </el-button>
    </header>
    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
    />
    <div class="ai-panel ai-chat__panel">
      <AnswerTranscript
        :messages="messages"
        :running="running"
        empty="连续对话，模型会记住本页之前的问答。&#10;换模型或清空对话后从头开始。"
      />
      <StreamStatsBar
        :stats="stats"
        :cost="cost"
      />
      <div class="ai-chat__input">
        <el-input
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 8 }"
          resize="none"
          aria-label="输入问题"
          placeholder="输入问题，Enter 发送，Shift + Enter 换行"
          @keydown="onKeydown"
        />
        <el-button
          v-if="running"
          @click="stop"
        >
          停止
        </el-button>
        <el-button
          v-else
          type="primary"
          :disabled="!canSend"
          @click="submit"
        >
          发送
        </el-button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.ai-chat { display: flex; flex-direction: column; gap: 12px; height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 480px; }
.ai-chat__bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.ai-chat__panel { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.ai-chat__input { display: flex; align-items: flex-end; gap: 10px; padding: 12px 18px; border-top: 1px solid var(--zt-border); }
</style>
