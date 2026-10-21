import { describe, expect, it } from 'vitest'

import type { ModelConfig } from '@/api/ai'
import { CREATE_DEFAULTS, EDIT_GROUPS, EDITOR_GROUPS, toBody, toRow } from './fields'

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

describe('模型配置表单转换', () => {
  it('列表显示中文，保存时换回代码值，来回不丢信息', () => {
    const row = toRow(flash)
    expect([row.provider, row.web_search, row.service_tier, row.thinking, row.reasoning_effort, row.enabled])
      .toEqual(['字节方舟', '联网', '低优（flex）', '开启', '低（low）', '启用'])
    const body = toBody(row as unknown as Record<string, string>)
    for (const key of Object.keys(body) as (keyof typeof body)[]) expect(body[key]).toEqual(flash[key])
  })

  it('「不传」和「停用」换回空串和 false', () => {
    const body = toBody({ ...CREATE_DEFAULTS, id: 'm', name: 'm', endpoint: 'ep', reasoning_effort: '不传', enabled: '停用' })
    expect([body.service_tier, body.reasoning_effort, body.enabled, body.web_search, body.sort_order]).toEqual(['', '', false, false, 100])
  })

  it('编辑时模型ID只读，新增时可填', () => {
    const idField = (groups: typeof EDITOR_GROUPS) => groups[0]?.fields.find(field => field.key === 'id')
    expect(idField(EDITOR_GROUPS)?.disabled).toBeFalsy()
    expect(idField(EDIT_GROUPS)?.disabled).toBe(true)
  })
})
