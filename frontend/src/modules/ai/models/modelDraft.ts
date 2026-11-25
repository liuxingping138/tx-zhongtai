import type { ModelConfig, ModelConfigBody } from '@/api/ai'
import { isValidPriceString } from './modelView'

export interface ModelDraft {
  id: string
  name: string
  provider: string
  endpoint: string
  enabled: boolean
  sort_order: string
  web_search: boolean
  service_tier: string
  thinking: string
  reasoning_effort: string
  rate_limit: string
  input_price: string
  output_price: string
  cache_price: string
  search_price: string
  flex_input_price: string
  flex_output_price: string
  peak_input_price: string
  peak_output_price: string
  peak_cache_price: string
  peak_hours: string
}

const ID_PATTERN = /^[\w.\-\u4e00-\u9fff]{1,64}$/
const PEAK_RANGE_PATTERN = /^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$/

export function createEmptyDraft(): ModelDraft {
  return {
    id: '',
    name: '',
    provider: 'ark',
    endpoint: '',
    enabled: true,
    sort_order: '100',
    web_search: false,
    service_tier: '',
    thinking: 'enabled',
    reasoning_effort: 'low',
    rate_limit: '',
    input_price: '',
    output_price: '',
    cache_price: '',
    search_price: '0',
    flex_input_price: '',
    flex_output_price: '',
    peak_input_price: '',
    peak_output_price: '',
    peak_cache_price: '',
    peak_hours: '',
  }
}

export function draftFromModel(item: ModelConfig): ModelDraft {
  return {
    id: item.id,
    name: item.name,
    provider: item.provider,
    endpoint: item.endpoint,
    enabled: item.enabled,
    sort_order: String(item.sort_order),
    web_search: item.web_search,
    service_tier: item.service_tier,
    thinking: item.thinking,
    reasoning_effort: item.reasoning_effort,
    rate_limit: item.rate_limit,
    input_price: item.input_price,
    output_price: item.output_price,
    cache_price: item.cache_price,
    search_price: item.search_price || '0',
    flex_input_price: item.flex_input_price,
    flex_output_price: item.flex_output_price,
    peak_input_price: item.peak_input_price,
    peak_output_price: item.peak_output_price,
    peak_cache_price: item.peak_cache_price,
    peak_hours: item.peak_hours,
  }
}

export function draftToBody(draft: ModelDraft): ModelConfigBody {
  const clean = (val: string) => val.trim()
  return {
    id: clean(draft.id),
    name: clean(draft.name),
    provider: clean(draft.provider),
    endpoint: clean(draft.endpoint),
    web_search: draft.web_search,
    thinking: clean(draft.thinking),
    reasoning_effort: draft.thinking === 'disabled' ? '' : clean(draft.reasoning_effort),
    service_tier: clean(draft.service_tier),
    input_price: clean(draft.input_price),
    output_price: clean(draft.output_price),
    flex_input_price: clean(draft.flex_input_price),
    flex_output_price: clean(draft.flex_output_price),
    peak_input_price: clean(draft.peak_input_price),
    peak_output_price: clean(draft.peak_output_price),
    peak_hours: clean(draft.peak_hours),
    cache_price: clean(draft.cache_price),
    peak_cache_price: clean(draft.peak_cache_price),
    search_price: draft.web_search ? clean(draft.search_price) || '0' : '0',
    rate_limit: clean(draft.rate_limit),
    enabled: draft.enabled,
    sort_order: Math.max(0, Math.min(100_000, Math.trunc(Number(clean(draft.sort_order)) || 0))),
  }
}

function clockMinutes(hour: number, minute: number, allowEnd24: boolean): number | null {
  if (allowEnd24 && hour === 24 && minute === 0) return 1440
  if (hour >= 24 || minute >= 60) return null
  return hour * 60 + minute
}

function validClockPart(part: string): boolean {
  const match = PEAK_RANGE_PATTERN.exec(part)
  if (!match) return false
  const start = clockMinutes(Number(match[1]), Number(match[2]), false)
  const end = clockMinutes(Number(match[3]), Number(match[4]), true)
  return start !== null && end !== null && start < end
}

function checkOptionalPrice(raw: string, label: string): string {
  const val = raw.trim()
  if (!val) return ''
  return isValidPriceString(val) ? '' : `${label}需填写 0 到 1000 之间的数字（最多 6 位小数）`
}

function validateBasicFields(draft: ModelDraft, isEdit: boolean): string {
  if (!isEdit && !ID_PATTERN.test(draft.id.trim())) {
    return '模型 ID 只能使用中英文、数字、点、横线和下划线，且不超过 64 字'
  }
  if (!draft.name.trim()) return '请填写显示名称'
  if (!draft.endpoint.trim()) return '请填写推理接入点'
  return ''
}

function validateOptionalPrices(draft: ModelDraft): string {
  const checks: [string, string][] = [
    [draft.cache_price, '上下文缓存命中单价'],
    [draft.flex_input_price, '低优输入单价'],
    [draft.flex_output_price, '低优输出单价'],
    [draft.peak_input_price, '高峰输入单价'],
    [draft.peak_output_price, '高峰输出单价'],
    [draft.peak_cache_price, '高峰缓存单价'],
  ]
  for (const [val, label] of checks) {
    const err = checkOptionalPrice(val, label)
    if (err) return err
  }
  return draft.web_search ? checkOptionalPrice(draft.search_price, '联网搜索单价') : ''
}

function validatePeakHoursIfNeeded(draft: ModelDraft): string {
  const hasPeak = Boolean(draft.peak_input_price.trim() || draft.peak_cache_price.trim())
  const hours = draft.peak_hours.trim()
  if (!hasPeak || !hours) return ''
  const parts = hours.split(/[,，;；\s]+/).filter(Boolean)
  return parts.length && parts.every(validClockPart)
    ? ''
    : '高峰时段格式有误，请按 09:00-12:00,14:00-18:00 填写'
}

function validatePairedPrices(draft: ModelDraft): string {
  const hasFlexIn = Boolean(draft.flex_input_price.trim())
  const hasFlexOut = Boolean(draft.flex_output_price.trim())
  if (hasFlexIn !== hasFlexOut) return '低优输入单价与低优输出单价需同时填写或同时留空'
  if (draft.service_tier === 'flex' && !hasFlexIn) return '服务档位已选「低优 flex」，请填写低优输入与输出单价'
  if (Boolean(draft.peak_input_price.trim()) !== Boolean(draft.peak_output_price.trim())) {
    return '高峰输入单价与高峰输出单价需同时填写或同时留空'
  }
  if (draft.peak_cache_price.trim() && !draft.cache_price.trim()) {
    return '填写高峰缓存单价前，请先填写平时的上下文缓存单价'
  }
  return validatePeakHoursIfNeeded(draft)
}

export function validateModelDraft(draft: ModelDraft, isEdit: boolean): string {
  const basicErr = validateBasicFields(draft, isEdit)
  if (basicErr) return basicErr
  if (!draft.input_price.trim() || !isValidPriceString(draft.input_price)) {
    return '请填写合法的常规输入单价（0 到 1000 之间，最多 6 位小数）'
  }
  if (!draft.output_price.trim() || !isValidPriceString(draft.output_price)) {
    return '请填写合法的常规输出单价（0 到 1000 之间，最多 6 位小数）'
  }
  return validateOptionalPrices(draft) || validatePairedPrices(draft)
}
