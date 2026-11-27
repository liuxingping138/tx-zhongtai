import { describe, expect, it } from 'vitest'

import {
  buildReportFacts,
  buildReportMetaSpecs,
  REPORT_EDITOR_GROUPS,
  REPORT_FILTER_DEFS,
  REPORT_FILTER_KEYS,
  REPORT_SUMMARY_KEYS,
  REPORT_SYSTEM_COLUMNS,
  REPORT_TABLE_COLUMNS,
  REPORT_TYPE_FALLBACK,
  validateReportForm,
} from './fields'

describe('报告库字段配置与校验', () => {
  it('包含全部 13 个报告业务字段与系统列', () => {
    const props = REPORT_TABLE_COLUMNS.map(col => col.prop)
    const expected13 = [
      'report_name',
      'project_name',
      'customer_name',
      'report_type',
      'industry_tags',
      'region_tag',
      'delivery_dept',
      'participants',
      'is_temp_support',
      'delivery_date',
      'summary',
      'keywords',
      'data_sources',
    ]
    for (const key of expected13) expect(props).toContain(key)
    expect(REPORT_TABLE_COLUMNS).toHaveLength(16)
    expect(REPORT_FILTER_KEYS).toContain('report_name')
    expect(REPORT_FILTER_DEFS).toHaveLength(13)
    expect(REPORT_SUMMARY_KEYS.length).toBeGreaterThan(0)
    expect(REPORT_SYSTEM_COLUMNS).toHaveLength(6)
    expect(REPORT_EDITOR_GROUPS).toHaveLength(3)
    expect(REPORT_TYPE_FALLBACK.length).toBeGreaterThan(0)
  })

  it('构建报告编辑表单规格：默认平滑回退兜底枚举', () => {
    const fallbackSpecs = buildReportMetaSpecs()
    expect(fallbackSpecs['基本信息']).toHaveLength(6)
    expect(fallbackSpecs['交付信息']).toHaveLength(4)
    expect(fallbackSpecs['内容摘要与来源']).toHaveLength(4)
    const regionSpec = fallbackSpecs['基本信息']!.find(s => s.key === 'region_tag')
    expect(regionSpec?.options).toContain('集团')
  })

  it('构建报告编辑表单规格：优先采用后端动态选项', () => {
    const dynamicSpecs = buildReportMetaSpecs({
      report_type: ['定制报告'],
      industry_tags: ['能源'],
      region_tag: ['广东省'],
      delivery_dept: ['政企部'],
      is_temp_support: ['是', '否'],
    })
    const basic = dynamicSpecs['基本信息']!
    const delivery = dynamicSpecs['交付信息']!
    expect(basic.find(s => s.key === 'report_type')?.options).toEqual(['定制报告'])
    expect(basic.find(s => s.key === 'industry_tags')?.options).toEqual(['能源'])
    expect(basic.find(s => s.key === 'region_tag')?.options).toEqual(['广东省'])
    expect(delivery.find(s => s.key === 'delivery_dept')?.options).toEqual(['政企部'])
  })

  it('校验报告名称必填与核心结论摘要≤100字', () => {
    expect(validateReportForm({ report_name: '   ', summary: '' })).toEqual({ report_name: '请填写报告名称' })
    expect(validateReportForm({ report_name: '年报', summary: '字'.repeat(101) })).toEqual({
      summary: '核心结论摘要不能超过 100 字',
    })
    expect(validateReportForm({ report_name: '年报', summary: '字'.repeat(100) })).toEqual({})
    expect(validateReportForm({ report_name: ['bad'], summary: ['bad'] })).toEqual({ report_name: '请填写报告名称' })
  })

  it('构建报告详情摘要栏 facts', () => {
    const full = buildReportFacts(
      {
        report_type: '行业研究报告',
        customer_name: '某集团',
        region_tag: '北京市',
        delivery_dept: '政企部',
        delivery_date: '2026-06-01',
        file_size_display: '2.5 MB',
        created_by_name: '张三',
        uploaded_at: '2026-06-01',
        updated_by_name: '李四',
        updated_at: '2026-06-02',
      },
      v => v,
    )
    expect(full).toHaveLength(8)
    expect(full.find(f => f.label === '报告类型')?.value).toBe('行业研究报告')
    expect(full.find(f => f.label === '上传')?.value).toBe('张三 · 2026-06-01')

    const empty = buildReportFacts({}, v => v)
    expect(empty.find(f => f.label === '报告类型')?.value).toBe('未定义')
    expect(empty.find(f => f.label === '客户名称')?.value).toBe('—')
  })
})
