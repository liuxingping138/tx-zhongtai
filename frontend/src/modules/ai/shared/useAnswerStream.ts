import { computed, reactive, ref } from 'vue'

import type { AiModel } from '@/api/ai'
import { errorMessage } from '@/api/errors'
import { postEventStream } from '@/api/eventStream'
import { costOf, type Usage } from './aiText'
import { applyStreamEvent } from './streamEvents'

export interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  reasoning: string
  /** 联网搜索等进行中的提示，回答结束后清空 */
  tip: string
  error: string
  time: string
  /** 试发带了输出字段时，答完按字段解析的结果；null 表示格式不对，没有这一项表示没解析 */
  parsed?: Record<string, string>[] | null
}

export interface StreamStats {
  model: AiModel | null
  thinking: boolean
  usage: Usage
}

function now(): string {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

/**
 * 试发的状态：消息列表、是否在回答、最近一次的模型与用量。
 * 事件协议见后端 app/application/asking.py。
 */
export function useAnswerStream() {
  const messages = ref<ChatMessage[]>([])
  const running = ref(false)
  const stats = reactive<StreamStats>({ model: null, thinking: false, usage: { input: 0, output: 0, search: 0, cached: 0 } })
  let controller: AbortController | null = null

  const cost = computed(() => costOf(stats.model ?? undefined, stats.usage))

  async function send(path: string, body: Record<string, unknown>, shown: string, thinking: boolean): Promise<void> {
    if (running.value) return
    const user = reactive<ChatMessage>({ role: 'user', text: shown, reasoning: '', tip: '', error: '', time: now() })
    const reply = reactive<ChatMessage>({ role: 'assistant', text: '', reasoning: '', tip: '', error: '', time: now() })
    messages.value.push(user, reply)
    stats.thinking = thinking
    stats.usage = { input: 0, output: 0, search: 0, cached: 0 }
    running.value = true
    controller = new AbortController()
    try {
      const target = { user, reply, stats }
      await postEventStream(path, body, event => applyStreamEvent(target, event), controller.signal)
      if (!reply.text && !reply.error) reply.error = '模型没有返回内容，请稍后重试'
    } catch (error) {
      reply.error = controller.signal.aborted ? '已停止生成' : errorMessage(error, '提问失败，请稍后重试')
    } finally {
      reply.tip = ''
      running.value = false
      controller = null
    }
  }

  function stop(): void {
    controller?.abort()
  }

  function clear(): void {
    stop()
    messages.value = []
    stats.model = null
    stats.usage = { input: 0, output: 0, search: 0, cached: 0 }
  }

  return { messages, running, stats, cost, send, stop, clear }
}
