<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Position } from '@element-plus/icons-vue'

import { chatModels, type AiModel } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import AnswerTranscript from '../shared/AnswerTranscript.vue'
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
const blocker = computed(() => (current.value && !current.value.available ? `${current.value.name} 的接口密钥未配置，换一个模型` : ''))

onMounted(async () => {
  try {
    models.value = await chatModels()
    modelId.value = models.value.find(item => item.available)?.id ?? models.value[0]?.id ?? ''
  } catch (error) {
    loadError.value = errorMessage(error, '模型列表加载失败，请刷新重试')
  }
})
onBeforeUnmount(stop)

/** 对话只在这一页里，清空就找不回来：有内容时先确认。 */
async function confirmClear(title: string, action: string): Promise<boolean> {
  if (!messages.value.length) return true
  return ElMessageBox.confirm('这段对话没有保存，清空后找不回来。需要的内容请先复制。', title, {
    type: 'warning', confirmButtonText: action, cancelButtonText: '取消',
  }).then(() => true, () => false)
}

/** 换模型等于换了一段上下文：服务端保存的上一轮回答属于原来的模型。 */
async function changeModel(next: string): Promise<void> {
  if (next === modelId.value) return
  if (!await confirmClear('换模型会清空这段对话', '换模型')) return
  clear()
  modelId.value = next
}

async function startOver(): Promise<void> {
  if (await confirmClear('开始新对话？', '清空并开始')) clear()
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
  <section class="ai-panel chat">
    <header class="chat__head">
      <h1>多轮对话</h1>
      <el-button
        :disabled="!messages.length || running"
        @click="startOver"
      >
        新对话
      </el-button>
    </header>
    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
    />
    <AnswerTranscript
      variant="chat"
      :messages="messages"
      :running="running"
      empty="有什么想问的？&#10;模型会记住这一页里之前的问答；换模型或点「新对话」就从头开始。"
    />
    <div class="chat__dock">
      <form
        class="chat__composer"
        @submit.prevent="submit"
      >
        <el-input
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 10 }"
          resize="none"
          aria-label="输入问题"
          placeholder="输入问题，Enter 发送，Shift + Enter 换行"
          @keydown="onKeydown"
        />
        <div class="chat__tools">
          <el-select
            :model-value="modelId"
            class="chat__model"
            size="small"
            aria-label="模型"
            placeholder="选择模型"
            @update:model-value="changeModel"
          >
            <el-option
              v-for="item in models"
              :key="item.id"
              :label="item.name"
              :value="item.id"
              :disabled="!item.available"
            >
              <span>{{ item.name }}</span>
              <span
                v-if="!item.available"
                class="chat__off"
              >未配置密钥</span>
            </el-option>
          </el-select>
          <el-switch
            v-if="current?.supports_thinking"
            v-model="thinking"
            size="small"
            active-text="深度思考"
          />
          <span
            v-if="blocker"
            class="chat__off"
          >{{ blocker }}</span>
          <span class="chat__spacer" />
          <el-button
            v-if="running"
            size="small"
            @click="stop"
          >
            停止
          </el-button>
          <el-button
            v-else
            type="primary"
            circle
            native-type="submit"
            :icon="Position"
            :disabled="!canSend"
            aria-label="发送"
          />
        </div>
      </form>
      <StreamStatsBar
        class="chat__stats"
        :stats="stats"
        :cost="cost"
      />
    </div>
  </section>
</template>

<style scoped>
.chat { display: flex; flex-direction: column; height: calc(100dvh - var(--workspace-header-height) - 48px); min-height: 520px; overflow: hidden; }
.chat__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 20px; border-bottom: 1px solid var(--zt-border); }
.chat__head h1 { margin: 0; color: var(--zt-ink-900); font-size: 15px; font-weight: 650; }
.chat__dock { padding: 0 max(20px, calc((100% - 820px) / 2)) 16px; }
.chat__composer { border: 1px solid var(--zt-border-strong); border-radius: 14px; background: var(--zt-panel); box-shadow: 0 6px 20px var(--zt-shadow-soft); transition: border-color 160ms ease, box-shadow 160ms ease; }
.chat__composer:focus-within { border-color: var(--el-color-primary-light-5); box-shadow: 0 6px 22px var(--zt-focus-ring); }
.chat__composer :deep(.el-textarea__inner) { padding: 14px 16px 4px; border: 0; box-shadow: none; background: transparent; font-size: 15px; line-height: 1.7; }
.chat__tools { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 6px 10px 10px 14px; }
.chat__model { width: 240px; }
.chat__spacer { flex: 1; }
.chat__off { margin-left: 8px; color: var(--zt-warning-text); font-size: 12px; }
.chat__stats { justify-content: center; border-top: 0; padding: 8px 0 0; }
@media (prefers-reduced-motion: reduce) {
  .chat__composer { transition: none; }
}
</style>
