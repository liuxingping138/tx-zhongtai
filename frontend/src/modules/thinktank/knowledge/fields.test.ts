import { describe, expect, it } from 'vitest'

import {
  buildKnowledgeFacts,
  buildMetaSectionSpecs,
  DETAIL_SYSTEM_COLUMNS,
  displayFileType,
  EDITABLE_FILE_TYPE_OPTIONS,
  FILE_TYPE_OPTIONS,
  FILTER_KEYS,
  INDUSTRY_OPTIONS,
  joinPipeTags,
  parseContentDispositionFilename,
  splitPipeTags,
  suffixTagType,
  TABLE_COLUMNS,
} from './fields'

describe('知识库字段与工具函数', () => {
  it('竖线分隔标签的拆分与拼接幂等且去空白', () => {
    expect(splitPipeTags('')).toEqual([])
    expect(splitPipeTags(null)).toEqual([])
    expect(splitPipeTags('中小| 教育 | 金融 ')).toEqual(['中小', '教育', '金融'])
    expect(joinPipeTags([' 中小 ', '', '教育'])).toBe('中小|教育')
  })

  it('文件类型展示与枚举保持完整', () => {
    expect(displayFileType('')).toBe('未定义')
    expect(displayFileType('产品')).toBe('产品')
    expect(FILE_TYPE_OPTIONS).toContain('未定义')
    expect(EDITABLE_FILE_TYPE_OPTIONS).not.toContain('未定义')
    expect(INDUSTRY_OPTIONS).toContain('无')
    expect(TABLE_COLUMNS).toHaveLength(14)
    expect(FILTER_KEYS).toContain('file_name')
    expect(DETAIL_SYSTEM_COLUMNS.length).toBeGreaterThan(0)
  })

  it('文件后缀颜色档位与下载文件名解析正确', () => {
    expect(suffixTagType('PDF')).toBe('danger')
    expect(suffixTagType('PPT')).toBe('warning')
    expect(suffixTagType('EXCEL')).toBe('success')
    expect(suffixTagType('WORD')).toBe('info')
    expect(suffixTagType('')).toBe('info')

    const header = "attachment; filename=\"fallback.xlsx\"; filename*=UTF-8''%E6%9C%AA%E5%AE%9A%E4%B9%89%E6%A0%87%E7%AD%BE%E6%95%B0%E6%8D%AE.xlsx"
    expect(parseContentDispositionFilename(header, 'default.xlsx')).toBe('未定义标签数据.xlsx')
    expect(parseContentDispositionFilename("attachment; filename*=UTF-8''%E0%A4%A", 'bad.xlsx')).toBe('bad.xlsx')
    expect(parseContentDispositionFilename('attachment; filename="report.pdf"', 'x.pdf')).toBe('report.pdf')
    expect(parseContentDispositionFilename('attachment;', 'x.pdf')).toBe('x.pdf')
    expect(parseContentDispositionFilename(undefined, 'x.pdf')).toBe('x.pdf')
  })

  it('构建详情摘要栏与分组编辑规格', () => {
    const factsFull = buildKnowledgeFacts(
      {
        prov_name: '北京',
        file_type: '产品',
        operator_type: '电信',
        depart_affiliation: '产数',
        data_time: '2026.03',
        file_size_display: '1.2 MB',
        created_by_name: '张三',
        uploaded_at: '2026-03-01',
        updated_by_name: '李四',
        updated_at: '2026-03-02',
      },
      v => v,
    )
    expect(factsFull).toHaveLength(8)
    expect(factsFull.find(f => f.label === '上传')?.value).toBe('张三 · 2026-03-01')

    const factsEmpty = buildKnowledgeFacts({}, v => v)
    expect(factsEmpty.find(f => f.label === '省份')?.value).toBe('—')
    expect(factsEmpty.find(f => f.label === '上传')?.value).toBe('—')

    expect(buildMetaSectionSpecs('基本信息', ['产品'], true, ['党政'], ['北京'])).toHaveLength(6)
    expect(buildMetaSectionSpecs('行业与产品标签', ['产品'], false, ['党政'], ['北京'])).toHaveLength(6)
    expect(buildMetaSectionSpecs('系统信息', ['产品'], false, ['党政'], ['北京'])).toEqual([])
  })
})
