import type { AiModel, RunStatus } from '@/api/ai'

/** 码表占位符：模板里写 @【上传码表】，提问时替换为整段码表文本。与后端 CODE_TABLE_FIELD 一致。 */
export const CODE_TABLE_FIELD = '上传码表'

export function splitFields(value: string): string[] {
  return value.split('|').map(item => item.trim()).filter(Boolean)
}

/** 「新增输出字段」拼成返回格式要求，追加到提示词末尾。措辞与旧系统一致，批量解析靠它约束模型输出。 */
export function outputFormatBlock(fields: string[]): string {
  const example = `[{${fields.map(field => `"${field}":"xx"`).join(',')}}]`
  return [
    '# 返回格式要求：',
    '1、不要编虚假信息，没有相关内容，用-填充。',
    `2、返回字段：${fields.join('、')}`,
    '3、最后以json格式返回给我，返回1条数据，不会要有多余的字段，严格按照我给的',
    `例如：${example}`,
    '注意两边有中括号！',
  ].join('\n')
}

export function appendBlock(content: string, block: string): string {
  return content.trim() ? `${content.replace(/\s+$/, '')}\n\n${block}` : block
}

/** 光标前最近的 @ 到光标之间没有空白时，返回 @ 位置和已输入的过滤词。 */
export function mentionAt(text: string, caret: number): { at: number; keyword: string } | null {
  const at = text.lastIndexOf('@', caret - 1)
  if (at < 0) return null
  const keyword = text.slice(at + 1, caret)
  if (/[\s【】]/.test(keyword)) return null
  return { at, keyword }
}

export function mentionOptions(headers: string[], hasCode: boolean, keyword: string): string[] {
  const all = hasCode ? [...headers, CODE_TABLE_FIELD] : headers
  const needle = keyword.trim().toLowerCase()
  return needle ? all.filter(item => item.toLowerCase().includes(needle)) : all
}

/** 用 @【列名】替换 @ 和过滤词，返回新文本和插入后的光标位置。 */
export function insertMention(text: string, at: number, caret: number, field: string): { text: string; caret: number } {
  const token = `@【${field}】`
  return { text: text.slice(0, at) + token + text.slice(caret), caret: at + token.length }
}

export interface Usage {
  input: number
  output: number
  search: number
}

export function costOf(model: Pick<AiModel, 'input_price' | 'output_price' | 'search_price'> | undefined, usage: Usage): { inference: number; search: number } {
  if (!model) return { inference: 0, search: 0 }
  return {
    inference: (usage.input / 1000) * Number(model.input_price) + (usage.output / 1000) * Number(model.output_price),
    search: usage.search * Number(model.search_price),
  }
}

/** 费用保留到小数点后 4 位：单次提问常在千分之一元量级。 */
export function formatYuan(value: number): string {
  return `¥${value.toFixed(4)}`
}

export const RUN_MODE_TEXT: Record<'test' | 'all', string> = { test: '测试 10 条', all: '运行全部' }

export const RUN_STATUS_TEXT: Record<RunStatus, string> = {
  queued: '排队中',
  running: '运行中',
  stopping: '停止中',
  done: '已完成',
  failed: '失败',
  cancelled: '已停止',
  interrupted: '已中断',
}

export function runStatusType(status: RunStatus): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'done') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'interrupted' || status === 'stopping') return 'warning'
  if (status === 'running' || status === 'queued') return 'primary'
  return 'info'
}

export function isActive(status: RunStatus): boolean {
  return status === 'queued' || status === 'running' || status === 'stopping'
}
