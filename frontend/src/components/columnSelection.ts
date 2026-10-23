/**
 * 列设置的记忆：恢复上次勾选的列。
 *
 * 只记勾了哪些列分不清「用户自己隐藏的列」和「上次之后页面新加的列」，新加的列会被当成隐藏。
 * 所以连同保存时页面上有哪些列一起记；不在那份清单里的列是新加的，按「默认展示全部字段」显示出来。
 * 没有清单的旧记录：分不清是隐藏的还是后加的，按「默认展示全部字段」都当新列显示（下次保存起就有清单了）。
 */
export function restoreColumns(saved: unknown, knownWhenSaved: unknown, current: readonly string[]): string[] | null {
  if (!Array.isArray(saved)) return null
  const currentSet = new Set(current)
  const keys = [...new Set(saved.filter((key): key is string => typeof key === 'string'))]
  const valid = keys.filter(key => currentSet.has(key))
  const known = Array.isArray(knownWhenSaved)
    ? new Set(knownWhenSaved.filter((key): key is string => typeof key === 'string'))
    : new Set(keys)
  const added = current.filter(key => !known.has(key) && !valid.includes(key))
  const restored = [...valid, ...added]
  return restored.length ? current.filter(key => restored.includes(key)) : null
}
