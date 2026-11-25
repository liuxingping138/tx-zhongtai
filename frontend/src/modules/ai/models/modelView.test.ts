import { describe, expect, it } from 'vitest'

import type { ModelConfig } from '@/api/ai'
import { createEmptyDraft, draftFromModel, draftToBody, validateModelDraft } from './modelDraft'
import {
  benchmarkSummary,
  filterModels,
  formatPricePair,
  formatUnitPrice,
  listExtraPrices,
  livePriceBadge,
  mainPriceDisplay,
  providerReadyState,
  serviceTierBadge,
  shortEndpoint,
  thinkingBadgeText,
} from './modelView'

const flexModel: ModelConfig = {
  id: 'deepseek-v4-flash',
  name: '字节-DeepSeek-V4-Flash（联网）',
  provider: 'ark',
  provider_name: '字节方舟',
  available: true,
  endpoint: 'ep-20260915173105-gv9tb',
  web_search: true,
  thinking: 'enabled',
  reasoning_effort: 'low',
  service_tier: 'flex',
  input_price: '0.003',
  output_price: '0.009',
  flex_input_price: '0.0015',
  flex_output_price: '0.0045',
  peak_input_price: '',
  peak_output_price: '',
  peak_hours: '',
  cache_price: '0.0001',
  peak_cache_price: '',
  search_price: '0.004',
  rate_limit: '500 RPM',
  enabled: true,
  sort_order: 10,
  version: 2,
  created_at: '2026-10-21 10:00:00',
  created_by_name: '系统',
  updated_at: '2026-10-22 10:15:00',
  updated_by_name: '系统管理员',
}

const economyModel: ModelConfig = {
  ...flexModel,
  id: 'deepseek-v41-flash',
  name: '字节-DeepSeek-V4.1-Flash经济版（不联网）',
  endpoint: 'ep-20261021162727-fcx55',
  web_search: false,
  service_tier: '',
  input_price: '0.0008',
  output_price: '0.0032',
  flex_input_price: '',
  flex_output_price: '',
  peak_input_price: '0.0016',
  peak_output_price: '0.0064',
  peak_hours: '09:00-12:00,14:00-18:00',
  cache_price: '0.000016',
  peak_cache_price: '0.000032',
  search_price: '0',
  sort_order: 30,
}

const baiduModel: ModelConfig = {
  ...flexModel,
  id: 'baidu-deepseek-v3.2',
  name: '百度-DeepSeek-V3.2',
  provider: 'baidu',
  provider_name: '百度千帆',
  available: false,
  endpoint: 'deepseek-v3.2',
  web_search: false,
  thinking: 'switch',
  reasoning_effort: '',
  service_tier: '',
  input_price: '0.001',
  output_price: '0.005',
  flex_input_price: '',
  flex_output_price: '',
  cache_price: '',
  search_price: '0',
  enabled: false,
  sort_order: 50,
}

describe('模型配置双口径计价与信息分层', () => {
  it('按百万与按千 token 精确无损换算，长接入点保留末尾唯一识别码', () => {
    expect(formatUnitPrice('', 'million')).toBe('—')
    expect(formatPricePair('', '', 'million')).toBe('—')
    expect(formatUnitPrice('0.000016', 'million')).toBe('¥0.016')
    expect(formatUnitPrice('0.000016', 'thousand')).toBe('0.000016')
    expect(formatPricePair('0.0008', '0.0032', 'million')).toBe('¥0.8 / ¥3.2')
    expect(livePriceBadge('0.0015')).toEqual({ text: '= ¥1.5 /百万', tone: 'primary' })
    expect(livePriceBadge('')).toEqual({ text: '未填', tone: 'muted' })
    expect(livePriceBadge('0.0000009')).toEqual({ text: '格式有误', tone: 'warn' })
    expect(shortEndpoint('ep-20260915173105-gv9tb')).toBe('ep-0915…gv9tb')
    expect(shortEndpoint('deepseek-v3.2')).toBe('deepseek-v3.2')
    expect(shortEndpoint('custom-very-long-model-endpoint-01')).toBe('custom-v…int-01')
  })

  it('列表生效单价与附加折算价单行紧凑表达，覆盖各档位与思考分支', () => {
    expect(mainPriceDisplay(flexModel, 'million')).toMatchObject({ pair: '¥1.5 / ¥4.5', tag: '低优', tagTone: 'amber' })
    expect(mainPriceDisplay(economyModel, 'million')).toMatchObject({ pair: '¥0.8 / ¥3.2', tag: '分时', tagTone: 'blue' })
    expect(mainPriceDisplay(baiduModel, 'thousand')).toMatchObject({ pair: '0.001 / 0.005', tag: '', tagTone: '' })
    expect(listExtraPrices(flexModel, 'million').chips.map(c => c.text)).toEqual(['缓 ¥0.1', '搜 ¥0.004/次'])
    expect(listExtraPrices(economyModel, 'million').chips.map(c => c.text)).toEqual(['峰 ¥1.6 / ¥6.4', '缓 ¥0.016·峰'])
    expect(listExtraPrices(baiduModel, 'million').chips.map(c => c.text)).toEqual(['按输入价计'])
    expect(serviceTierBadge('flex')).toEqual({ text: '低优 flex', tone: 'amber' })
    expect(serviceTierBadge('auto')).toEqual({ text: '常规 auto', tone: 'blue' })
    expect(serviceTierBadge('')).toEqual({ text: '默认档', tone: 'muted' })
    expect(thinkingBadgeText(flexModel)).toBe('思考开启·low')
    expect(thinkingBadgeText({ thinking: 'disabled', reasoning_effort: 'low' })).toBe('思考关闭')
    expect(thinkingBadgeText({ thinking: '', reasoning_effort: '' })).toBe('默认思考')
  })

  it('基准价自动选启用模型中最低输入档，处理无启用模型与未知密钥状态', () => {
    expect(benchmarkSummary([])).toBeNull()
    expect(benchmarkSummary([baiduModel])).toBeNull()
    const items = [flexModel, economyModel, baiduModel]
    expect(benchmarkSummary(items)).toEqual({
      pair: '入 ¥0.8 · 出 ¥3.2',
      sub: '/百万（缓存 ¥0.016）',
      name: '字节-DeepSeek-V4.1-Flash经济版（不联网）',
    })
    expect(providerReadyState(items, 'ark')).toBe('ready')
    expect(providerReadyState(items, 'baidu')).toBe('missing')
    expect(providerReadyState(items, 'other')).toBe('unknown')
    expect(providerReadyState([{ ...baiduModel, available: undefined }], 'baidu')).toBe('unknown')
  })

  it('支持多维筛选及按名称、单价、排序权重升降序排列', () => {
    const items = [baiduModel, economyModel, flexModel]
    expect(filterModels(items, { provider: 'all', status: 'all', webOnly: false, keyword: '' }).map(m => m.id))
      .toEqual(['deepseek-v4-flash', 'deepseek-v41-flash', 'baidu-deepseek-v3.2'])
    expect(filterModels(items, { provider: 'all', status: 'all', webOnly: false, keyword: '' }, 'price', false).map(m => m.id))
      .toEqual(['deepseek-v4-flash', 'baidu-deepseek-v3.2', 'deepseek-v41-flash'])
    expect(filterModels(items, { provider: 'all', status: 'all', webOnly: false, keyword: '' }, 'name', true).length).toBe(3)
    expect(filterModels(items, { provider: 'ark', status: 'on', webOnly: true, keyword: 'gv9tb' }).map(m => m.id))
      .toEqual(['deepseek-v4-flash'])
    expect(filterModels(items, { provider: 'all', status: 'off', webOnly: false, keyword: 'deepseek-v3.2' }).map(m => m.id))
      .toEqual(['baidu-deepseek-v3.2'])
  })

  it('编辑草稿联动与全分支防呆校验和后端规则严格一致', () => {
    const draft = createEmptyDraft()
    expect(validateModelDraft(draft, false)).toContain('模型 ID')
    draft.id = 'test-model'
    expect(validateModelDraft(draft, false)).toContain('显示名称')
    draft.name = '测试模型'
    expect(validateModelDraft(draft, false)).toContain('推理接入点')
    draft.endpoint = 'ep-test'
    expect(validateModelDraft(draft, false)).toContain('常规输入单价')
    draft.input_price = '0.001'
    expect(validateModelDraft(draft, false)).toContain('常规输出单价')
    draft.output_price = '0.004'
    expect(validateModelDraft(draft, true)).toBe('')

    draft.web_search = true
    draft.search_price = 'bad'
    expect(validateModelDraft(draft, true)).toContain('联网搜索单价')
    draft.search_price = '0.004'

    draft.service_tier = 'flex'
    expect(validateModelDraft(draft, false)).toContain('低优')
    draft.flex_input_price = '0.0005'
    expect(validateModelDraft(draft, false)).toContain('同时填写')
    draft.flex_output_price = '0.002'
    expect(validateModelDraft(draft, false)).toBe('')

    draft.peak_input_price = '0.002'
    expect(validateModelDraft(draft, false)).toContain('高峰输入')
    draft.peak_output_price = '0.008'

    draft.peak_cache_price = '0.0002'
    expect(validateModelDraft(draft, false)).toContain('缓存单价')
    draft.cache_price = '0.0001'
    draft.peak_hours = 'bad-format'
    expect(validateModelDraft(draft, false)).toContain('高峰时段')
    draft.peak_hours = '25:00-26:00'
    expect(validateModelDraft(draft, false)).toContain('高峰时段')
    draft.peak_hours = '18:00-24:00'
    expect(validateModelDraft(draft, false)).toBe('')

    const roundtrip = draftFromModel({ ...flexModel, search_price: '' })
    expect(roundtrip.search_price).toBe('0')
    roundtrip.web_search = true
    roundtrip.search_price = ''
    roundtrip.sort_order = ''
    const body = draftToBody(roundtrip)
    expect(body.search_price).toBe('0')
    expect(body.sort_order).toBe(0)
  })
})
