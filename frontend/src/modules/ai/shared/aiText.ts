import type { AiModel, BatchRun, RunStatus } from '@/api/ai'

/** 码表占位符：模板里写 @【上传码表】，提问时替换为整段码表文本。与后端 CODE_TABLE_FIELD 一致。 */
export const CODE_TABLE_FIELD = '上传码表'

export function splitFields(value: string): string[] {
  return value.split('|').map(item => item.trim()).filter(Boolean)
}

/** 「新增输出字段」拼成返回格式要求，追加到提示词末尾。措辞与旧系统一致，批量解析靠它约束模型输出。 */
export function outputFormatBlock(fields: string[]): string {
  return [
    '# 返回格式要求：',
    '1、不要编虚假信息，没有相关内容，用-填充。',
    `2、返回字段：${fields.join('、')}`,
    '3、最后以json格式返回给我，返回1条数据，不会要有多余的字段，严格按照我给的',
    `例如：${formatExample(fields)}`,
    '注意两边有中括号！',
  ].join('\n')
}

function formatExample(fields: string[]): string {
  return `[{${fields.map(field => `"${field}":"xx"`).join(',')}}]`
}

export function appendBlock(content: string, block: string): string {
  return content.trim() ? `${content.replace(/\s+$/, '')}\n\n${block}` : block
}

// 格式要求里写字段的两行：「2、返回字段：a、b」和「例如：[{"a":"xx","b":"xx"}]」。编号、冒号全半角都认，人手改过的旧模板也能对上。
const FIELDS_LINE = /^(\s*(?:\d+[、.．]\s*)?返回字段[：:]\s*)(.*)$/
const EXAMPLE_LINE = /^(\s*例如[：:]\s*)\[\{.*\}\]\s*$/

/** 提示词里「返回字段」那一行写的字段；没有这一行时是 null：模板没用标准的格式要求，不拿来比。 */
export function promptFields(content: string): string[] | null {
  for (const line of content.split('\n')) {
    const match = FIELDS_LINE.exec(line)
    if (match) return (match[2] ?? '').split(/[、,，|]/).map(item => item.trim()).filter(Boolean)
  }
  return null
}

export type FormatState = 'none' | 'match' | 'stale'

/** 提示词里的格式要求和输出字段对不对得上：none 没写格式要求，match 字段一致（顺序不论），stale 改了输出字段没跟着改。 */
export function formatState(content: string, fields: string[]): FormatState {
  const written = promptFields(content)
  if (!written || !fields.length) return 'none'
  const same = written.length === fields.length && fields.every(field => written.includes(field))
  return same ? 'match' : 'stale'
}

/** 按现在的输出字段改写格式要求：只换「返回字段」和「例如」两行，其余措辞、位置不动；没有这两行就在末尾追加整段。 */
export function refreshFormatBlock(content: string, fields: string[]): string {
  if (!promptFields(content)) return appendBlock(content, outputFormatBlock(fields))
  const example = formatExample(fields)
  return content.split('\n').map(line => {
    const head = FIELDS_LINE.exec(line)?.[1]
    if (head !== undefined) return `${head}${fields.join('、')}`
    const sample = EXAMPLE_LINE.exec(line)?.[1]
    return sample === undefined ? line : `${sample}${example}`
  }).join('\n')
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
  /** 输入里命中上下文缓存的 token（含在 input 里），按缓存单价计费 */
  cached: number
}

type PricedModel = Pick<AiModel, 'input_price' | 'output_price' | 'search_price'> & Partial<Pick<AiModel, 'cache_price'>>

/** 和后端 llm_models.calc_costs 同一口径：未命中的输入按输入价、命中缓存的按缓存价（没给缓存价按输入价）、输出按输出价。 */
export function costOf(model: PricedModel | undefined, usage: Usage): { inference: number; search: number } {
  if (!model) return { inference: 0, search: 0 }
  const cached = Math.min(Math.max(usage.cached || 0, 0), Math.max(usage.input, 0))
  const cachePrice = model.cache_price ? Number(model.cache_price) : Number(model.input_price)
  return {
    inference: ((usage.input - cached) / 1000) * Number(model.input_price)
      + (cached / 1000) * cachePrice
      + (usage.output / 1000) * Number(model.output_price),
    search: usage.search * Number(model.search_price),
  }
}

/** 缓存命中率：命中缓存的输入 ÷ 全部输入，取整到 0.1%；没有命中（或没有输入）返回空串，页面就不显示。 */
export function cacheHitText(input: number, cached: number): string {
  if (!input || !cached || cached <= 0) return ''
  return `${String(Number(((Math.min(cached, input) / input) * 100).toFixed(1)))}%`
}

/** 费用保留到小数点后 4 位：单次提问常在千分之一元量级。 */
/** 去掉多余的小数位：3.0000000004 → 3，0.80 → 0.8 */
function plain(value: number): string {
  return String(Number(value.toFixed(4)))
}

/** 下拉里的价：此刻适用的单价，库里按每千 token 存、这里换成每百万 token 好读；写明是哪一档，联网另按次计。 */
export function priceText(model: Pick<AiModel, 'input_price' | 'output_price' | 'search_price' | 'web_search' | 'price_note'>): string {
  const perMillion = (value: string) => plain(Number(value) * 1000)
  const parts = [`输入 ¥${perMillion(model.input_price)} · 输出 ¥${perMillion(model.output_price)} /百万 token`]
  if (model.price_note) parts.push(model.price_note)
  if (model.web_search && Number(model.search_price)) parts.push(`联网搜索 ¥${plain(Number(model.search_price))}/次`)
  return parts.join(' · ')
}

/** 试发底栏等紧凑位置的单行价格摘要，完整分时计价说明由外层 title 悬停展示。 */
export function compactPriceText(model: Pick<AiModel, 'input_price' | 'output_price' | 'web_search'>): string {
  const perMillion = (value: string) => plain(Number(value) * 1000)
  return `输入 ¥${perMillion(model.input_price)} · 输出 ¥${perMillion(model.output_price)} /百万 token${model.web_search ? ' · 含联网' : ''}`
}

export interface SmartModelParts {
  family: string
  tier: string
  online: boolean
}

function splitOnlineSuffix(raw: string): { text: string; online: boolean } {
  const online = /[（(]联网[）)]/.test(raw)
  const text = raw
    .replace(/[（(](?:不联网|联网)[）)]/g, '')
    .replace(/版$/g, '')
    .trim()
  return { text, online }
}

/** 列表高辨识度模型拆解：去掉冗余厂商前缀，拆成「主家族版本 + 档位后缀 + 是否联网」，避免整列截成相同的 DeepSeek-V4... */
export function smartModelParts(rawName: string): SmartModelParts {
  if (!rawName) return { family: '未选', tier: '', online: false }
  const stripped = rawName.replace(/^(字节|百度|阿里|腾讯|智谱)\s*[-－]\s*/, '').trim()
  const { text, online } = splitOnlineSuffix(stripped)
  const ds = /^(DeepSeek)[-－\s]*(V[\d.]+|R\d+)(?:[-－\s]*(.+))?$/i.exec(text)
  if (ds) {
    const ver = ds[2] ?? ''
    const rest = (ds[3] ?? '').replace(/版$/g, '').trim()
    return { family: `DeepSeek ${ver}`, tier: rest, online }
  }
  const doubao = /^(Doubao)[-－\s]*([\d.]+[-－]?(?:Pro|Lite|Seed)?)(?:[-－\s]*(.+))?$/i.exec(text)
  if (doubao) {
    const ver = (doubao[2] ?? '').replace(/[-－]/g, ' ')
    const rest = (doubao[3] ?? '').replace(/版$/g, '').trim()
    return { family: `Doubao ${ver}`, tier: rest, online }
  }
  return { family: text || stripped, tier: '', online }
}

export function formatYuan(value: number): string {
  return `¥${value.toFixed(4)}`
}

export const RUN_MODE_TEXT: Record<'test' | 'all', string> = { test: '只跑前几条', all: '运行全部' }

/** 批量任务列表里的来源：样本试跑只在模板页看，不出现在这里。 */
export const RUN_SOURCE_TEXT: Record<'manual' | 'pipeline', string> = { manual: '页面发起', pipeline: '定时任务' }

export function runModeText(run: Pick<BatchRun, 'row_limit'>): string {
  return run.row_limit > 0 ? `前 ${run.row_limit} 条` : '全部'
}

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

/**
 * 自动重跑的轮次（批量任务、定时任务一次最多跑三轮，第 2、3 轮隔一会儿只重问网络失败、格式不对的行）。
 * 第 1 轮不说；运行中写「第 2 轮：重问 35 条，14:05 开始」，结束后写「共跑 3 轮」。
 */
export function roundText(run: Pick<BatchRun, 'status' | 'retry_round' | 'round_rows' | 'round_starts_at'>): string {
  if (run.retry_round <= 1) return ''
  if (!isActive(run.status)) return `共跑 ${run.retry_round} 轮`
  const at = run.round_starts_at ? `，${run.round_starts_at.slice(11, 16)} 开始` : ''
  return `第 ${run.retry_round} 轮：重问上一轮网络失败或格式不对的 ${run.round_rows} 条${at}`
}
