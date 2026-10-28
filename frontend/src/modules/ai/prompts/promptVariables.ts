import { CODE_TABLE_FIELD } from '../shared/aiText'

/** 变量写法与后端 templating 一致：@【列名】。 */
const VARIABLE = /@【([^【】\n]+)】/g

/** column 能换成 Excel 列；code 换成码表全文；pending 还没传测试样本、没法核对；missing 样本里没有这一列；nocode 用了码表变量但没选码表 */
export type VariableState = 'column' | 'code' | 'pending' | 'missing' | 'nocode'

export interface PromptSegment {
  text: string
  /** 普通文字为空；变量按能否替换分三种，编辑器据此上色 */
  state?: VariableState
}

export interface UsedVariable {
  name: string
  state: VariableState
  count: number
}

/** 能替换成什么：Excel 有这一列、码表（有码表时）、或者哪都找不到——批量时会原样留在提示词里。
 * 还没传测试样本时列名没法核对，标成 pending，不当成写错。 */
export function variableState(name: string, headers: readonly string[], hasCode: boolean): VariableState {
  if (name === CODE_TABLE_FIELD) return hasCode ? 'code' : 'nocode'
  if (!headers.length) return 'pending'
  return headers.includes(name) ? 'column' : 'missing'
}

/** 把提示词切成普通文字和变量片段，编辑器背景层按片段画出变量标记。 */
export function promptSegments(text: string, headers: readonly string[], hasCode: boolean): PromptSegment[] {
  const segments: PromptSegment[] = []
  let last = 0
  for (const match of text.matchAll(VARIABLE)) {
    const start = match.index ?? 0
    if (start > last) segments.push({ text: text.slice(last, start) })
    segments.push({ text: match[0], state: variableState(match[1] ?? '', headers, hasCode) })
    last = start + match[0].length
  }
  if (last < text.length) segments.push({ text: text.slice(last) })
  return segments
}

/** 提示词里用到的变量，按第一次出现的顺序去重并计数。 */
export function usedVariables(text: string, headers: readonly string[], hasCode: boolean): UsedVariable[] {
  const found = new Map<string, UsedVariable>()
  for (const match of text.matchAll(VARIABLE)) {
    const name = match[1] ?? ''
    const item = found.get(name)
    if (item) item.count += 1
    else found.set(name, { name, state: variableState(name, headers, hasCode), count: 1 })
  }
  return [...found.values()]
}

/** Excel 里有、提示词还没用到的列，作为可点击插入的候选。 */
export function unusedColumns(text: string, headers: readonly string[]): string[] {
  const used = new Set([...text.matchAll(VARIABLE)].map(match => match[1]))
  return headers.filter(header => !used.has(header))
}
