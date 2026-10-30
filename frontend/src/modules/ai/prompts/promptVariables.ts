import { CODE_TABLE_FIELD } from '../shared/aiText'

/** 变量写法和后端 templating._VAR_RE 一字不差：@【列名】，列名去掉首尾空白。
 * 原来前端不认换行和「【」、也不去空白：「@【 政策正文 】」前端标不能用、后端照常替换；
 * 「@【政策\n正文】」前端显示正常、后端选模板时拦下。 */
export const VARIABLE = /@【([^】]+)】/g

/** 变量的列名：和后端 template_variables 一样去掉首尾空白。 */
export function variableName(match: RegExpMatchArray): string {
  return (match[1] ?? '').trim()
}

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
    segments.push({ text: match[0], state: variableState(variableName(match), headers, hasCode) })
    last = start + match[0].length
  }
  if (last < text.length) segments.push({ text: text.slice(last) })
  return segments
}

/** 提示词里用到的变量，按第一次出现的顺序去重并计数。 */
export function usedVariables(text: string, headers: readonly string[], hasCode: boolean): UsedVariable[] {
  const found = new Map<string, UsedVariable>()
  for (const match of text.matchAll(VARIABLE)) {
    const name = variableName(match)
    const item = found.get(name)
    if (item) item.count += 1
    else found.set(name, { name, state: variableState(name, headers, hasCode), count: 1 })
  }
  return [...found.values()]
}

/** Excel 里有、提示词还没用到的列，作为可点击插入的候选。 */
export function unusedColumns(text: string, headers: readonly string[]): string[] {
  const used = new Set([...text.matchAll(VARIABLE)].map(variableName))
  return headers.filter(header => !used.has(header))
}
