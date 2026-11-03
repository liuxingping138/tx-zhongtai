import type { DataColumn } from './dataColumns'
import type { EditorGroup } from './editorGroups'

export interface DetailField {
  column: DataColumn
  /** 长文本占整行，短字段两个一行。 */
  wide: boolean
}

export interface DetailSection {
  title: string
  fields: DetailField[]
}

/** 编辑表单里没有的列（编码、关联主键、入库和更新记录等）归到这一组，放在最后。 */
export const SYSTEM_SECTION = '系统信息'

/**
 * 详情按编辑表单的分组排，查看和编辑是同一套分类；表单里没有的列收进「系统信息」。
 * 没有表单分组的页面（如只读的爬虫监测）整页一组、不加标题。
 */
export function buildDetailSections(columns: readonly DataColumn[], groups: readonly EditorGroup[] = []): DetailSection[] {
  const byProp = new Map(columns.map(col => [col.prop, col]))
  const grouped = new Set<string>()
  const sections: DetailSection[] = groups.map(group => ({
    title: group.title,
    fields: group.fields.map((field) => {
      grouped.add(field.key)
      // 列表里叠成一格的列（如「行业」），详情照样按各自的字段名一行一项
      const found = byProp.get(field.key)
      const column = found && !found.stack ? found : { prop: field.key, label: field.label }
      return { column, wide: Boolean(field.long || column.wrap) }
    }),
  }))
  const rest = columns.filter(col => !grouped.has(col.prop)).map(column => ({ column, wide: Boolean(column.wrap) }))
  if (rest.length) sections.push({ title: groups.length ? SYSTEM_SECTION : '', fields: rest })
  return sections.filter(section => section.fields.length)
}

/**
 * 排成表格的行：短字段两个一行，长字段独占一行。
 * 长字段前面落单的短字段也独占一行（值占满剩下的宽度），不和下一行错位。
 */
export function detailRows(fields: readonly DetailField[]): DetailField[][] {
  const rows: DetailField[][] = []
  let pending: DetailField | undefined
  for (const field of fields) {
    if (field.wide) {
      if (pending) rows.push([pending])
      pending = undefined
      rows.push([field])
    } else if (pending) {
      rows.push([pending, field])
      pending = undefined
    } else {
      pending = field
    }
  }
  if (pending) rows.push([pending])
  return rows
}
