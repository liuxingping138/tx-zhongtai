/**
 * 一条记录拆成好几行时（如一条政策解读出十几行行业场景），按挨着的相同标题分组：
 * 每组前面插一行分组标题条，表格里不再逐行写标题。只分挨着的，翻页后下一页开头再起一组。
 */
export interface GroupRow<T> {
  id: string
  group: { title: string; rows: T[] }
}

export function groupConsecutive<T extends { id: string }>(
  items: readonly T[],
  titleOf: (row: T) => string,
): (T | GroupRow<T>)[] {
  const out: (T | GroupRow<T>)[] = []
  let current: GroupRow<T> | null = null
  for (const row of items) {
    const title = titleOf(row)
    if (!current || current.group.title !== title) {
      // 分组行的 id 带上第一行的 id：同页两段同名标题（中间隔着别的）也不会撞 row-key。
      current = { id: `group:${row.id}`, group: { title, rows: [] } }
      out.push(current)
    }
    current.group.rows.push(row)
    out.push(row)
  }
  return out
}

export function isGroupRow<T>(row: unknown): row is GroupRow<T> {
  return typeof row === 'object' && row !== null && 'group' in row
}
