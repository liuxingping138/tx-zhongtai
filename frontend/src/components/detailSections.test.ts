import { describe, expect, it } from 'vitest'
import type { DataColumn } from './dataColumns'
import { SYSTEM_SECTION, buildDetailSections, detailRows, type DetailField } from './detailSections'
import type { EditorGroup } from './editorGroups'

const columns: DataColumn[] = [
  { prop: 'title', label: '标题', minWidth: 300 },
  { prop: 'industry', label: '一级行业', width: 120 },
  { prop: 'summary', label: '要文', width: 320, wrap: true },
  { prop: 'created_at', label: '入库时间', width: 190, time: true },
]
const groups: EditorGroup[] = [
  { title: '基本信息', hint: '', fields: [{ key: 'title', label: '标题' }, { key: 'tenant_id', label: '租户标识' }] },
  { title: '解读内容', hint: '', fields: [{ key: 'industry', label: '一级行业' }, { key: 'summary', label: '要文', long: true }] },
]

describe('detail sections', () => {
  it('follows the editor groups and puts columns outside the form into system info', () => {
    const sections = buildDetailSections(columns, groups)
    expect(sections.map(section => section.title)).toEqual(['基本信息', '解读内容', SYSTEM_SECTION])
    expect(sections[0]!.fields.map(field => field.column.prop)).toEqual(['title', 'tenant_id'])
    expect(sections[2]!.fields.map(field => field.column.prop)).toEqual(['created_at'])
  })

  it('keeps the table column definition so times and links format the same as the list', () => {
    const field = buildDetailSections(columns, groups)[2]!.fields[0]!
    expect(field.column.time).toBe(true)
  })

  it('列表里叠成一格的列（如「行业」），详情照样按各自的字段名一行一项', () => {
    const stacked: DataColumn[] = [{ prop: 'industry', label: '行业', stack: ['industry_l2'] }]
    const sections = buildDetailSections(stacked, [{ title: '行业', hint: '', fields: [{ key: 'industry', label: '一级行业' }, { key: 'industry_l2', label: '二级行业' }] }])
    expect(sections[0]!.fields.map(field => field.column.label)).toEqual(['一级行业', '二级行业'])
  })

  it('marks long editor fields and wrapping columns as full-width', () => {
    const [, content] = buildDetailSections(columns, groups)
    expect(content!.fields.map(field => field.wide)).toEqual([false, true])
  })

  it('shows one untitled section when the page has no editor', () => {
    const sections = buildDetailSections(columns)
    expect(sections).toHaveLength(1)
    expect(sections[0]!.title).toBe('')
    expect(sections[0]!.fields).toHaveLength(4)
  })
})

describe('detail rows', () => {
  const short = (prop: string): DetailField => ({ column: { prop, label: prop }, wide: false })
  const long = (prop: string): DetailField => ({ column: { prop, label: prop }, wide: true })
  const props = (rows: DetailField[][]) => rows.map(row => row.map(field => field.column.prop))

  it('pairs short fields and gives long ones a row of their own', () => {
    expect(props(detailRows([short('a'), short('b'), long('c'), short('d')]))).toEqual([['a', 'b'], ['c'], ['d']])
  })

  it('lets a lone short field before a long one take its own row instead of misaligning', () => {
    expect(props(detailRows([short('a'), long('b'), short('c'), short('d')]))).toEqual([['a'], ['b'], ['c', 'd']])
  })
})
