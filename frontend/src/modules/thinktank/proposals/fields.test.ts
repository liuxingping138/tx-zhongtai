import { describe, expect, it } from 'vitest'

import {
  BIDDING_METHOD_FALLBACK,
  buildProposalFacts,
  buildProposalMetaSpecs,
  OPPORTUNITY_SOURCE_FALLBACK,
  PROPOSAL_EDITOR_GROUPS,
  PROPOSAL_FILTER_DEFS,
  PROPOSAL_FILTER_KEYS,
  PROPOSAL_SUMMARY_KEYS,
  PROPOSAL_SYSTEM_COLUMNS,
  PROPOSAL_TABLE_COLUMNS,
  PROPOSAL_TYPE_FALLBACK,
  proposalResultTag,
  validateProposalForm,
} from './fields'

describe('方案库字段配置与校验', () => {
  it('包含全部 14 个方案业务字段与系统列', () => {
    const props = PROPOSAL_TABLE_COLUMNS.map(col => col.prop)
    const expected14 = [
      'proposal_name',
      'customer_name',
      'proposal_type',
      'industry_tags',
      'region_tag',
      'opportunity_source',
      'bidding_method',
      'bid_deadline',
      'owner_dept',
      'owner_name',
      'quote_amount',
      'result_status',
      'win_amount',
      'selling_points',
    ]
    for (const key of expected14) expect(props).toContain(key)
    expect(PROPOSAL_TABLE_COLUMNS).toHaveLength(17)
    expect(PROPOSAL_FILTER_KEYS).toContain('proposal_name')
    expect(PROPOSAL_FILTER_DEFS).toHaveLength(13)
    expect(PROPOSAL_SUMMARY_KEYS.length).toBeGreaterThan(0)
    expect(PROPOSAL_SYSTEM_COLUMNS).toHaveLength(6)
    expect(PROPOSAL_EDITOR_GROUPS).toHaveLength(3)
    expect(PROPOSAL_TYPE_FALLBACK.length).toBeGreaterThan(0)
    expect(OPPORTUNITY_SOURCE_FALLBACK.length).toBeGreaterThan(0)
    expect(BIDDING_METHOD_FALLBACK.length).toBeGreaterThan(0)
  })

  it('构建方案编辑表单规格：优先动态选项并平滑回退兜底', () => {
    const fallbackSpecs = buildProposalMetaSpecs()
    expect(fallbackSpecs['基本信息']).toHaveLength(7)
    expect(fallbackSpecs['招投标与报价']).toHaveLength(6)
    expect(fallbackSpecs['核心卖点与备注']).toHaveLength(2)

    const dynamicSpecs = buildProposalMetaSpecs({
      proposal_type: ['定制方案'],
      industry_tags: ['金融'],
      region_tag: ['上海市'],
      opportunity_source: ['客户直委'],
      bidding_method: ['公开招标'],
      owner_dept: ['市场部'],
      result_status: ['中标'],
    })
    expect(dynamicSpecs['基本信息']?.find(s => s.key === 'proposal_type')?.options).toEqual(['定制方案'])
    expect(dynamicSpecs['基本信息']?.find(s => s.key === 'owner_dept')?.options).toEqual(['市场部'])
    expect(dynamicSpecs['招投标与报价']?.find(s => s.key === 'opportunity_source')?.options).toEqual(['客户直委'])
    expect(dynamicSpecs['招投标与报价']?.find(s => s.key === 'result_status')?.options).toEqual(['中标'])
  })

  it('校验方案名称必填与卖点摘要≤100字', () => {
    expect(validateProposalForm({ proposal_name: '', selling_points: '' })).toEqual({ proposal_name: '请填写方案名称' })
    expect(validateProposalForm({ proposal_name: '云网方案', selling_points: '卖'.repeat(101) })).toEqual({
      selling_points: '方案核心卖点摘要不能超过 100 字',
    })
    expect(validateProposalForm({ proposal_name: '云网方案', selling_points: '卖'.repeat(100) })).toEqual({})
    expect(validateProposalForm({ proposal_name: [], selling_points: [] })).toEqual({ proposal_name: '请填写方案名称' })
  })

  it('解析方案结果徽标颜色与摘要 facts', () => {
    expect(proposalResultTag('中标')).toEqual({ label: '中标', type: 'success' })
    expect(proposalResultTag('未中标')).toEqual({ label: '未中标', type: 'danger' })
    expect(proposalResultTag('待定')).toEqual({ label: '待定', type: 'warning' })
    expect(proposalResultTag('流标')).toEqual({ label: '流标', type: 'info' })
    expect(proposalResultTag('其他状态')).toEqual({ label: '其他状态', type: 'info' })
    expect(proposalResultTag('')).toBeNull()
    expect(proposalResultTag(null)).toBeNull()

    const full = buildProposalFacts(
      {
        proposal_type: '投标方案',
        customer_name: '某省厅',
        region_tag: '江苏省',
        owner_dept: '政企部',
        owner_name: '王五',
        quote_amount: '120',
        win_amount: '115',
        file_size_display: '4.1 MB',
        created_by_name: '张三',
        uploaded_at: '2026-06-01',
        updated_by_name: '李四',
        updated_at: '2026-06-02',
      },
      v => v,
    )
    expect(full).toHaveLength(10)
    expect(full.find(f => f.label === '报价(万元)')?.value).toBe('120')

    const empty = buildProposalFacts({}, v => v)
    expect(empty.find(f => f.label === '方案类型')?.value).toBe('未定义')
    expect(empty.find(f => f.label === '中标金额(万元)')?.value).toBe('—')
  })
})
