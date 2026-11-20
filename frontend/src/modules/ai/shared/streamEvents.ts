import type { AiModel } from '@/api/ai'
import type { Usage } from './aiText'

export interface StreamTarget {
  user: { text: string }
  reply: { text: string; reasoning: string; tip: string; error: string; parsed?: Record<string, string>[] | null }
  stats: { model: AiModel | null; usage: Usage }
}

type Handler = (target: StreamTarget, value: unknown) => void

function applyUsage(target: StreamTarget, value: unknown): void {
  const usage = value as { input_tokens?: number; output_tokens?: number; cached_tokens?: number; web_search?: number }
  target.stats.usage.input = usage.input_tokens ?? 0
  target.stats.usage.output = usage.output_tokens ?? 0
  target.stats.usage.cached = usage.cached_tokens ?? 0
  if (typeof usage.web_search === 'number') target.stats.usage.search = usage.web_search
}

function applyTool(target: StreamTarget, value: unknown): void {
  const tool = value as { stage?: string; message?: string }
  target.reply.tip = tool.message ?? ''
  // 没有 usage 里的权威次数时按进度事件计数，usage 到了会覆盖。
  if (tool.stage === 'web_search_in_progress') target.stats.usage.search += 1
}

/** 一种事件一个处理函数；未知事件忽略，后端以后加新事件不会让页面出错。事件协议见后端 asking.py。 */
const HANDLERS: Record<string, { type: 'string' | 'object'; apply: Handler }> = {
  prompt: { type: 'string', apply: (t, v) => { t.user.text = v as string } },
  model: { type: 'object', apply: (t, v) => { t.stats.model = v as AiModel } },
  text: { type: 'string', apply: (t, v) => { t.reply.text += v as string } },
  reasoning: { type: 'string', apply: (t, v) => { t.reply.reasoning += v as string } },
  tool_event: { type: 'object', apply: applyTool },
  usage: { type: 'object', apply: applyUsage },
  error: { type: 'string', apply: (t, v) => { t.reply.error = v as string } },
}

export function applyStreamEvent(target: StreamTarget, event: Record<string, unknown>): void {
  // 试发答完按输出字段解析的结果：null 也有意义（格式不对），不能像别的事件一样跳过。
  if ('parsed' in event) target.reply.parsed = Array.isArray(event.parsed) ? event.parsed as Record<string, string>[] : null
  for (const [key, value] of Object.entries(event)) {
    const handler = HANDLERS[key]
    if (handler && value !== null && typeof value === handler.type) handler.apply(target, value)
  }
}
