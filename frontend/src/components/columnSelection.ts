/**
 * 列设置的记忆：恢复上次勾选的列。
 *
 * 只记勾了哪些列分不清「用户自己隐藏的列」和「上次之后页面新加的列」，新加的列会被当成隐藏。
 * 所以连同保存时页面上有哪些列一起记；不在那份清单里的列是新加的，按「默认展示全部字段」显示出来。
 * 没有清单的旧记录：记着的列里有页面上已经不存在的，说明列改过，现有而没记着的都当新列显示。
 */
export function restoreColumns(saved: unknown, knownWhenSaved: unknown, current: readonly string[]): string[] | null {
  if (!Array.isArray(saved)) return null
  const currentSet = new Set(current)
  const keys = [...new Set(saved.filter((key): key is string => typeof key === 'string'))]
  const valid = keys.filter(key => currentSet.has(key))
  const known = Array.isArray(knownWhenSaved)
    ? new Set(knownWhenSaved.filter((key): key is string => typeof key === 'string'))
    : keys.length > valid.length ? new Set(keys) : null
  const added = known ? current.filter(key => !known.has(key) && !valid.includes(key)) : []
  const restored = [...valid, ...added]
  return restored.length ? current.filter(key => restored.includes(key)) : null
}
