import { ref } from 'vue'

import type { DataColumn } from '@/components/dataColumns'
import type { EditorGroup } from '@/components/editorGroups'

/**
 * 业务表的全部列：先是表格列，再补上编辑表单里有、表格里没有的字段，列设置和详情都按这份展示。
 * 默认全部显示；用户在列设置里的选择由 ColumnPicker 记在浏览器里。
 */
export function useDetailColumns(tableColumns: readonly DataColumn[], groups: readonly EditorGroup[]) {
  // 叠进别的列里显示的下级字段（stack）不再单独成列
  const known = new Set(tableColumns.flatMap(col => [col.prop, ...(col.stack ?? [])]))
  const extra = groups
    .flatMap(group => group.fields)
    .filter(field => !known.has(field.key))
    .map(field => ({ prop: field.key, label: field.label }))
  const columns: DataColumn[] = [...tableColumns, ...extra]
  const defaults = columns.map(col => col.prop)
  return { columns, defaults, selected: ref([...defaults]) }
}
