<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import type { ChatMessage } from './useAnswerStream'

const props = defineProps<{ messages: ChatMessage[]; running: boolean; empty: string }>()
const box = ref<HTMLElement | null>(null)

// 回答过程中跟随到底部；用户往上翻看时不强行拉回。
watch(
  () => props.messages.map(item => item.text.length + item.reasoning.length).join(','),
  async () => {
    const element = box.value
    if (!element) return
    const nearBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 120
    await nextTick()
    if (nearBottom) element.scrollTop = element.scrollHeight
  },
)
</script>

<template>
  <div
    ref="box"
    class="transcript"
    role="log"
    aria-live="polite"
  >
    <p
      v-if="!messages.length"
      class="transcript__empty"
    >
      {{ empty }}
    </p>
    <article
      v-for="(message, index) in messages"
      :key="index"
      class="transcript__item"
      :class="`transcript__item--${message.role}`"
    >
      <header class="transcript__meta">
        {{ message.role === 'user' ? '提问' : '回答' }} · {{ message.time }}
      </header>
      <details
        v-if="message.reasoning"
        class="transcript__reasoning"
        :open="running && index === messages.length - 1 && !message.text"
      >
        <summary>思考过程</summary>
        <pre>{{ message.reasoning }}</pre>
      </details>
      <pre
        v-if="message.text"
        class="transcript__text"
      >{{ message.text }}</pre>
      <p
        v-if="message.tip"
        class="transcript__tip"
      >
        {{ message.tip }}…
      </p>
      <p
        v-else-if="running && index === messages.length - 1 && !message.text && !message.error"
        class="transcript__tip"
      >
        正在等待模型回答…
      </p>
      <el-alert
        v-if="message.error"
        :title="message.error"
        type="error"
        :closable="false"
        show-icon
      />
    </article>
  </div>
</template>

<style scoped>
.transcript { flex: 1; min-height: 0; overflow: auto; padding: 16px 18px; display: flex; flex-direction: column; gap: 14px; }
.transcript__empty { margin: auto; color: var(--zt-ink-500); font-size: 13px; text-align: center; line-height: 1.8; white-space: pre-line; }
.transcript__item { max-width: 92%; padding: 10px 14px; border: 1px solid var(--zt-border); border-radius: var(--zt-radius); background: var(--zt-panel); }
.transcript__item--user { align-self: flex-end; background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-7); }
.transcript__item--assistant { align-self: flex-start; }
.transcript__meta { margin-bottom: 6px; color: var(--zt-ink-500); font-size: 12px; }
.transcript__text, .transcript__reasoning pre { margin: 0; font: inherit; font-size: 14px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; color: var(--zt-ink-900); }
.transcript__reasoning { margin-bottom: 8px; padding: 6px 10px; border-left: 3px solid var(--zt-border); background: var(--zt-soft); border-radius: 4px; }
.transcript__reasoning summary { cursor: pointer; color: var(--zt-ink-500); font-size: 12px; }
.transcript__reasoning pre { margin-top: 6px; color: var(--zt-ink-700); font-size: 13px; }
.transcript__tip { margin: 6px 0 0; color: var(--zt-ink-500); font-size: 12px; }
.transcript__item .el-alert { margin-top: 8px; }
</style>
