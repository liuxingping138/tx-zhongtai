/** 上线前看草稿比线上版本改了哪几行：按行做最长公共子序列，没变的长段折叠起来。 */

export type DiffKind = 'same' | 'add' | 'del'
export interface DiffLine { kind: DiffKind; text: string }
export type DiffBlock = DiffLine | { kind: 'fold'; count: number }

// 几百行的提示词足够；两边都上千行时 LCS 表太大，直接整段对照。
const MAX_CELLS = 1_000_000

/** common(i, j)：a[i..] 和 b[j..] 的最长公共子序列长度，按行铺平存一张表。 */
function commonLengths(a: string[], b: string[]): (i: number, j: number) => number {
  const width = b.length + 1
  const table = new Int32Array((a.length + 1) * width)
  const common = (i: number, j: number): number => table[i * width + j] ?? 0
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i * width + j] = a[i] === b[j] ? common(i + 1, j + 1) + 1 : Math.max(common(i + 1, j), common(i, j + 1))
    }
  }
  return common
}

export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.split('\n')
  const b = after.split('\n')
  const del = (text: string): DiffLine => ({ kind: 'del', text })
  const add = (text: string): DiffLine => ({ kind: 'add', text })
  if (a.length * b.length > MAX_CELLS) return [...a.map(del), ...b.map(add)]
  const common = commonLengths(a, b)
  const lines: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    const left = a[i] ?? ''
    const right = b[j] ?? ''
    if (left === right) {
      lines.push({ kind: 'same', text: left })
      i++
      j++
    } else if (common(i + 1, j) >= common(i, j + 1)) {
      lines.push(del(left))
      i++
    } else {
      lines.push(add(right))
      j++
    }
  }
  return [...lines, ...a.slice(i).map(del), ...b.slice(j).map(add)]
}

/** 改动上下各留 context 行，其余没变的折叠成「未改动 N 行」。 */
export function foldUnchanged(lines: DiffLine[], context = 2): DiffBlock[] {
  const keep = lines.map(() => false)
  lines.forEach((line, index) => {
    if (line.kind === 'same') return
    for (let k = Math.max(0, index - context); k <= Math.min(lines.length - 1, index + context); k++) keep[k] = true
  })
  const blocks: DiffBlock[] = []
  let folded = 0
  lines.forEach((line, index) => {
    if (keep[index]) {
      if (folded) blocks.push({ kind: 'fold', count: folded })
      folded = 0
      blocks.push(line)
    } else {
      folded++
    }
  })
  if (folded) blocks.push({ kind: 'fold', count: folded })
  return blocks
}
