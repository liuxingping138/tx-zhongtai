/**
 * 挨着的相同值合成一格：返回每行跨几行，一段相同值的第一行跨整段，其余为 0（不画）。
 * 政策解读列表里，同一条政策解读出的十几行只写一次标题。
 */
export function repeatSpans(values: readonly string[]): number[] {
  const spans = values.map(() => 1)
  let start = 0
  values.forEach((value, index) => {
    if (index > 0 && value === values[start]) {
      spans[start]! += 1
      spans[index] = 0
    } else {
      start = index
    }
  })
  return spans
}
