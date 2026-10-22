import { CODE_TABLE_FIELD } from '../shared/aiText'

/** 变量写法与后端 templating 一致：@【列名】。 */
const VARIABLE = /@【([^【】\n]+)】/g

export type VariableState = 'column' | 'code' | 'missing'

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

/** 能替换成什么：Excel 有这一列、码表（有码表时）、或者哪都找不到——批量时会原样留在提示词里。 */
export function variableState(name: string, headers: readonly string[], hasCode: boolean): VariableState {
  if (name === CODE_TABLE_FIELD) return hasCode ? 'code' : 'missing'
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
