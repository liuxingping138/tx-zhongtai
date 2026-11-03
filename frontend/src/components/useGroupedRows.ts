import { computed, type ComputedRef, type Ref } from 'vue'

import { groupConsecutive, isGroupRow, type GroupRow } from './rowGroups'

export interface SelectableTable<Row> {
  clearSelection: () => void
  toggleRowSelection: (row: Row, selected?: boolean) => void
  getSelectionRows: () => Row[]
}

/**
 * BusinessTable 的分组标题条：按挨着的相同标题在每组前插一行，这一行除勾选列外合成一格；
 * 勾标题条勾整组，组里的行都勾上了标题条跟着勾上，往外报的勾选只有真正的行。
 */
export function useGroupedRows<T extends { id: string }>(options: {
  items: () => readonly T[]
  titleOf: (row: T) => string
  enabled: () => boolean
  selectable: () => boolean
  /** 除勾选列外一共几列（数据列、补位列、操作列）。 */
  otherColumns: ComputedRef<number>
  table: Ref<SelectableTable<T | GroupRow<T>> | undefined>
  emitSelection: (rows: T[]) => void
}) {
  type TableRow = T | GroupRow<T>
  const isGroup = (row: TableRow): row is GroupRow<T> => isGroupRow<T>(row)
  const rows = computed<TableRow[]>(() => (options.enabled()
    ? groupConsecutive(options.items(), options.titleOf)
    : [...options.items()]))
  /** 行在当前页的位置（不算分组标题条）：核对页按它翻上一条、下一条。 */
  const positions = computed(() => new Map(options.items().map((row, index) => [row.id, index])))
  const at = (row: T) => positions.value.get(row.id) ?? 0

  function spanMethod({ row, columnIndex }: { row: TableRow; columnIndex: number }): [number, number] {
    if (!isGroup(row)) return [1, 1]
    const first = options.selectable() ? 1 : 0
    if (columnIndex < first) return [1, 1]
    return columnIndex === first ? [1, options.otherColumns.value] : [0, 0]
  }
  const rowClass = ({ row }: { row: TableRow }) => (isGroup(row) ? 'group-row' : '')

  const report = (selection: TableRow[]) => options.emitSelection(selection.filter((row): row is T => !isGroup(row)))
  // 同步勾选时 Element 每勾一行都会发 selection-change：同步期间不往外报，完了按最终勾选报一次。
  let syncing = false
  function onSelect(selection: TableRow[], row: TableRow) {
    const table = options.table.value
    if (syncing || !table) return
    syncing = true
    try {
      if (isGroup(row)) {
        const on = selection.includes(row)
        for (const child of row.group.rows) table.toggleRowSelection(child, on)
      } else {
        const group = rows.value.find((item): item is GroupRow<T> => isGroup(item) && item.group.rows.includes(row))
        if (group) table.toggleRowSelection(group, group.group.rows.every(child => selection.includes(child)))
      }
    } finally {
      syncing = false
    }
    report(table.getSelectionRows())
  }
  function onSelectionChange(selection: TableRow[]) {
    if (!syncing) report(selection)
  }

  return { rows, at, isGroup, spanMethod, rowClass, onSelect, onSelectionChange }
}
