import type { ModelConfig, ModelConfigBody } from '@/api/ai'

export type PriceUnit = 'million' | 'thousand'
export type ProviderFilter = 'all' | 'ark' | 'baidu'
export type StatusFilter = 'all' | 'on' | 'off'
export type BadgeTone = 'muted' | 'warn' | 'primary'
export type ModelSortKey = 'sort_order' | 'name' | 'price'

export interface ModelFilters {
  provider: ProviderFilter
  status: StatusFilter
  webOnly: boolean
  keyword: string
}

export interface ExtraPriceChip {
  text: string
  tone: 'amber' | 'green' | 'teal' | 'muted'
}

const DECIMAL_PATTERN = /^\d+(?:\.\d{1,6})?$/
const ARK_EP_PATTERN = /^ep-\d{4}(\d{4})\d+-([a-z0-9]+)$/i

export const PROVIDER_LABELS: Record<string, string> = {
  ark: '字节方舟',
  baidu: '百度千帆',
}

export const THINKING_SHORT_LABELS: Record<string, string> = {
  enabled: '思考开启',
  switch: '思考可选',
  disabled: '思考关闭',
  '': '默认思考',
}

export const THINKING_DETAIL_LABELS: Record<string, string> = {
  enabled: '开启',
  switch: '提问时可选（千帆开关）',
  disabled: '关闭',
  '': '按模型默认（不传）',
}

export const EFFORT_DETAIL_LABELS: Record<string, string> = {
  low: '低（low）',
  high: '高（high）',
  max: '最高（max）',
  '': '按模型默认（不传）',
}

export const SERVICE_TIER_DETAIL_LABELS: Record<string, string> = {
  flex: '低优（flex）',
  auto: '常规（auto）',
  '': '按模型默认（不传）',
}

export function plainDecimal(value: number): string {
  return String(Number(value.toFixed(6)))
}

export function isValidPriceString(raw: string): boolean {
  const trimmed = raw.trim()
  if (!DECIMAL_PATTERN.test(trimmed)) return false
  const num = Number(trimmed)
  return Number.isFinite(num) && num >= 0 && num < 1000
}

export function formatUnitPrice(raw: string, unit: PriceUnit): string {
  const trimmed = raw.trim()
  if (!trimmed || !Number.isFinite(Number(trimmed))) return '—'
  const num = Number(trimmed)
  return unit === 'million' ? `¥${plainDecimal(num * 1000)}` : plainDecimal(num)
}

export function formatPricePair(inRaw: string, outRaw: string, unit: PriceUnit): string {
  if (!inRaw.trim() && !outRaw.trim()) return '—'
  return `${formatUnitPrice(inRaw, unit)} / ${formatUnitPrice(outRaw, unit)}`
}

export function livePriceBadge(raw: string): { text: string; tone: BadgeTone } {
  const trimmed = raw.trim()
  if (!trimmed) return { text: '未填', tone: 'muted' }
  if (!isValidPriceString(trimmed)) return { text: '格式有误', tone: 'warn' }
  return { text: `= ¥${plainDecimal(Number(trimmed) * 1000)} /百万`, tone: 'primary' }
}

/** 长方舟接入点保留日期与末尾唯一识别码（如 ep-0915…gv9tb），避免常规右截断把不同接入点都裁成一样的 ep-20260915... */
export function shortEndpoint(endpoint: string): string {
  const match = ARK_EP_PATTERN.exec(endpoint.trim())
  if (match) return `ep-${match[1]}…${match[2]}`
  return endpoint.length > 18 ? `${endpoint.slice(0, 8)}…${endpoint.slice(-6)}` : endpoint
}

export function effectiveInputNumber(item: ModelConfig): number {
  const raw = item.service_tier === 'flex' && item.flex_input_price ? item.flex_input_price : item.input_price
  return Number(raw) || 0
}

export function mainPriceDisplay(
  item: ModelConfig,
  unit: PriceUnit,
): { pair: string; tag: string; tagTone: 'amber' | 'blue' | ''; tooltip: string } {
  const isFlex = item.service_tier === 'flex' && Boolean(item.flex_input_price)
  if (isFlex) {
    const pair = formatPricePair(item.flex_input_price, item.flex_output_price, unit)
    const reg = formatPricePair(item.input_price, item.output_price, unit)
    return {
      pair,
      tag: '低优',
      tagTone: 'amber',
      tooltip: `低优实付：${pair}；常规备选：${reg}（入库原值 ${item.flex_input_price} / ${item.flex_output_price} 元/千）`,
    }
  }
  const pair = formatPricePair(item.input_price, item.output_price, unit)
  if (item.peak_input_price) {
    const peak = formatPricePair(item.peak_input_price, item.peak_output_price, unit)
    const hours = item.peak_hours || '09:00-12:00,14:00-18:00'
    return { pair, tag: '分时', tagTone: 'blue', tooltip: `空闲常规：${pair}；工作日高峰（${hours}）：${peak}` }
  }
  return {
    pair,
    tag: '',
    tagTone: '',
    tooltip: `全天常规：${formatPricePair(item.input_price, item.output_price, 'million')} /百万（原值 ${item.input_price} / ${item.output_price} 元/千）`,
  }
}

export function listExtraPrices(item: ModelConfig, unit: PriceUnit): { chips: ExtraPriceChip[]; tooltip: string } {
  const chips: ExtraPriceChip[] = []
  const notes: string[] = []
  if (item.peak_input_price) {
    const peak = formatPricePair(item.peak_input_price, item.peak_output_price, unit)
    chips.push({ text: `峰 ${peak}`, tone: 'amber' })
    notes.push(`工作日高峰（${item.peak_hours || '09:00-12:00,14:00-18:00'}）：${peak}`)
  }
  if (item.cache_price) {
    const base = formatUnitPrice(item.cache_price, unit)
    const suffix = item.peak_cache_price ? '·峰' : ''
    chips.push({ text: `缓 ${base}${suffix}`, tone: 'green' })
    notes.push(
      item.peak_cache_price
        ? `缓存命中：平时 ${base} / 高峰 ${formatUnitPrice(item.peak_cache_price, unit)}`
        : `缓存命中：${base}`,
    )
  }
  if (item.web_search) {
    const search = plainDecimal(Number(item.search_price || '0'))
    chips.push({ text: `搜 ¥${search}/次`, tone: 'teal' })
    notes.push(`联网搜索附加费：¥${search} / 次`)
  }
  if (!chips.length) {
    return {
      chips: [{ text: '按输入价计', tone: 'muted' }],
      tooltip: '全天同一单价，未单独配置缓存价（命中缓存按输入单价计），不开启联网搜索',
    }
  }
  return { chips, tooltip: notes.join('；') }
}

export function thinkingBadgeText(item: Pick<ModelConfig, 'thinking' | 'reasoning_effort'>): string {
  const base = THINKING_SHORT_LABELS[item.thinking] ?? (item.thinking || '默认思考')
  if (item.thinking === 'disabled' || !item.reasoning_effort) return base
  return `${base}·${item.reasoning_effort}`
}

export function serviceTierBadge(tier: string): { text: string; tone: 'amber' | 'blue' | 'muted' } {
  if (tier === 'flex') return { text: '低优 flex', tone: 'amber' }
  if (tier === 'auto') return { text: '常规 auto', tone: 'blue' }
  return { text: '默认档', tone: 'muted' }
}

export function providerReadyState(items: ModelConfig[], provider: string): 'ready' | 'missing' | 'unknown' {
  const matched = items.filter(item => item.provider === provider)
  if (!matched.length) return 'unknown'
  if (matched.some(item => item.available === true)) return 'ready'
  if (matched.some(item => item.available === false)) return 'missing'
  return 'unknown'
}

export function benchmarkSummary(items: ModelConfig[]): { pair: string; sub: string; name: string } | null {
  const enabled = items.filter(item => item.enabled)
  if (!enabled.length) return null
  const best = [...enabled].sort((a, b) => effectiveInputNumber(a) - effectiveInputNumber(b))[0]
  if (!best) return null
  const isFlex = best.service_tier === 'flex' && Boolean(best.flex_input_price)
  const inVal = formatUnitPrice(isFlex ? best.flex_input_price : best.input_price, 'million')
  const outVal = formatUnitPrice(isFlex ? best.flex_output_price : best.output_price, 'million')
  const cachePart = best.cache_price ? `（缓存 ${formatUnitPrice(best.cache_price, 'million')}）` : ''
  return { pair: `入 ${inVal} · 出 ${outVal}`, sub: `/百万${cachePart}`, name: best.name }
}

function matchesKeyword(item: ModelConfig, needle: string): boolean {
  if (!needle) return true
  return (
    item.name.toLowerCase().includes(needle)
    || item.id.toLowerCase().includes(needle)
    || item.endpoint.toLowerCase().includes(needle)
  )
}

function compareModels(a: ModelConfig, b: ModelConfig, sortKey: ModelSortKey, sortAsc: boolean): number {
  const factor = sortAsc ? 1 : -1
  if (sortKey === 'name') return a.name.localeCompare(b.name, 'zh-CN') * factor
  if (sortKey === 'price') {
    const diff = effectiveInputNumber(a) - effectiveInputNumber(b)
    return diff !== 0 ? diff * factor : a.sort_order - b.sort_order
  }
  return (a.sort_order - b.sort_order) * factor || a.id.localeCompare(b.id)
}

export function filterModels(
  items: ModelConfig[],
  filters: ModelFilters,
  sortKey: ModelSortKey = 'sort_order',
  sortAsc = true,
): ModelConfig[] {
  const needle = filters.keyword.trim().toLowerCase()
  return items
    .filter(item => filters.provider === 'all' || item.provider === filters.provider)
    .filter(item => filters.status === 'all' || (filters.status === 'on' ? item.enabled : !item.enabled))
    .filter(item => !filters.webOnly || item.web_search)
    .filter(item => matchesKeyword(item, needle))
    .sort((a, b) => compareModels(a, b, sortKey, sortAsc))
}

export type { ModelConfigBody }
