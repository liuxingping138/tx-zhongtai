import { describe, expect, it } from 'vitest'

import type { ModelConfig } from '@/api/ai'
import {
  checkModelForm,
  CREATE_DEFAULTS,
  DEFAULT_SELECTED_COLUMNS,
  EDIT_GROUPS,
  EDITOR_GROUPS,
  formatMillionSummary,
  priceCellTitle,
  TABLE_COLUMNS,
  toBody,
  toMillionYuan,
  toRow,
  withLivePriceHints,
} from './fields'

const flash: ModelConfig = {
  id: 'deepseek-v4-flash',
  name: '字节-DeepSeek-V4-Flash（联网）',
  provider: 'ark',
  provider_name: '字节方舟',
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
  version: 3,
  created_at: '',
  created_by_name: '',
  updated_at: '',
  updated_by_name: '',
}

describe('模型配置表单转换与轻量计价辅助', () => {
  it('列表显示中文，保存时换回代码值，来回不丢信息', () => {
    const row = toRow(flash)
    expect([row.provider, row.web_search, row.service_tier, row.thinking, row.reasoning_effort, row.enabled])
      .toEqual(['字节方舟', '联网', '低优（flex）', '开启', '低（low）', '启用'])
    const body = toBody(row as unknown as Record<string, string>)
    for (const key of Object.keys(body) as (keyof typeof body)[]) expect(body[key]).toEqual(flash[key])
  })

  it('「按模型默认」和「停用」换回空串和 false', () => {
    const body = toBody({ ...CREATE_DEFAULTS, id: 'm', name: 'm', endpoint: 'ep', reasoning_effort: '按模型默认', enabled: '停用' })
    expect([body.service_tier, body.reasoning_effort, body.enabled, body.web_search, body.sort_order]).toEqual(['', '', false, false, 100])
  })

  it('缓存单价进表单、列表和保存的请求体，没填时是空串（后端按输入价算）', () => {
    const fields = EDITOR_GROUPS.flatMap(group => group.fields).map(field => field.key)
    expect(fields).toEqual(expect.arrayContaining(['cache_price', 'peak_cache_price']))
    const props = TABLE_COLUMNS.map(col => col.prop)
    expect(props.indexOf('cache_price')).toBeGreaterThan(props.indexOf('peak_output_price'))
    expect(props.indexOf('peak_cache_price')).toBe(props.indexOf('cache_price') + 1)
    const body = toBody({ ...CREATE_DEFAULTS, id: 'm', name: 'm', endpoint: 'ep', cache_price: ' 0.000016 ', peak_cache_price: '0.000032' })
    expect([body.cache_price, body.peak_cache_price]).toEqual(['0.000016', '0.000032'])
    expect(toBody({ ...CREATE_DEFAULTS, id: 'm' }).cache_price).toBe('')
  })

  it('编辑时模型ID只读，新增时可填', () => {
    const idField = (groups: typeof EDITOR_GROUPS) => groups[0]?.fields.find(field => field.key === 'id')
    expect(idField(EDITOR_GROUPS)?.disabled).toBeFalsy()
    expect(idField(EDIT_GROUPS)?.disabled).toBe(true)
  })

  it('列表把名称、状态、档位与价格放前面，模型ID与接入点放留痕列之前，默认勾选核心常用列', () => {
    const props = TABLE_COLUMNS.map(col => col.prop)
    expect(props.slice(0, 6)).toEqual(['name', 'enabled', 'provider', 'web_search', 'service_tier', 'input_price'])
    expect(props.slice(-4)).toEqual(['id', 'endpoint', 'updated_at', 'updated_by_name'])
    expect(DEFAULT_SELECTED_COLUMNS.every(col => props.includes(col))).toBe(true)
  })

  it('价格说明实时附注每百万 token 换算值，悬停与详情摘要不产生浮点尾巴', () => {
    expect(toMillionYuan('0.000016')).toBe('¥0.016')
    expect(toMillionYuan('bad')).toBe('')
    expect(toMillionYuan('1500')).toBe('')
    expect(priceCellTitle('0.0008')).toBe('0.0008 元/千 token（即 ¥0.8 / 百万 token）')
    expect(priceCellTitle('')).toBe('')

    const groups = withLivePriceHints(EDITOR_GROUPS, { input_price: '0.0008', cache_price: '0.00002' })
    const priceFields = groups[2]?.fields ?? []
    expect(priceFields.find(f => f.key === 'input_price')?.hint).toContain('¥0.8 / 百万 token')
    expect(priceFields.find(f => f.key === 'cache_price')?.hint).toContain('¥0.02 / 百万 token')
    expect(priceFields.find(f => f.key === 'output_price')?.hint).toBe('元/千 token')

    const economyRow = toRow({
      ...flash,
      peak_input_price: '0.0016',
      peak_output_price: '0.0064',
      peak_cache_price: '0.000032',
    })
    expect(formatMillionSummary(economyRow)).toContain('常规 ¥3 / ¥9')
    expect(formatMillionSummary(economyRow)).toContain('低优 ¥1.5 / ¥4.5')
    expect(formatMillionSummary(economyRow)).toContain('高峰 ¥1.6 / ¥6.4')
    expect(formatMillionSummary(economyRow)).toContain('缓存 ¥0.1（高峰 ¥0.032）')
    expect(formatMillionSummary(toRow({ ...flash, input_price: '', output_price: '', flex_input_price: '', flex_output_price: '', cache_price: '' }))).toBe('')
  })

  it('保存前成对单价校验准确落到对应字段', () => {
    expect(checkModelForm({ ...CREATE_DEFAULTS, input_price: '0.001', output_price: '0.002' })).toBeUndefined()
    expect(checkModelForm({ ...CREATE_DEFAULTS, flex_input_price: '0.001' })?.key).toBe('flex_output_price')
    expect(checkModelForm({ ...CREATE_DEFAULTS, flex_output_price: '0.002' })?.key).toBe('flex_input_price')
    expect(checkModelForm({ ...CREATE_DEFAULTS, service_tier: '低优（flex）' })?.key).toBe('flex_input_price')
    expect(checkModelForm({ ...CREATE_DEFAULTS, peak_input_price: '0.002' })?.key).toBe('peak_output_price')
    expect(checkModelForm({ ...CREATE_DEFAULTS, peak_cache_price: '0.0001' })?.key).toBe('cache_price')
  })
})
