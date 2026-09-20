import type { DataColumn } from './dataColumns'

/** Keep short fields fixed; readable text columns share the remaining surface. */
export function layoutDataColumns(columns: readonly DataColumn[], available: number, actionWidth: number) {
  const widths = columns.map(col => col.width ?? col.minWidth ?? 140)
  const flexible = columns.map((col, index) => ({ col, index }))
    .filter(({ col }) => !col.width && (col.grow ?? 0) > 0)
  const weight = flexible.reduce((sum, { col }) => sum + col.grow!, 0)
  let remaining = Math.max(0, Math.floor(available) - actionWidth - widths.reduce((sum, width) => sum + width, 0))
  const budget = remaining
  flexible.forEach(({ col, index }, position) => {
    const extra = position === flexible.length - 1 ? remaining : Math.floor(budget * col.grow! / weight)
    widths[index]! += extra
    remaining -= extra
  })
  return columns.map((col, index) => ({ ...col, width: widths[index]! }))
}
