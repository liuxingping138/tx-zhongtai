import type { BatchRun, RunRow, RunRowStatus, SampleSummary } from '@/api/ai'
import type { SampleCompare } from '@/api/aiSamples'

/**
 * 样本试跑结果怎么讲给人听：逐行状态、要看哪几行、和上一次比变了什么，试发一行之后和试跑结果比。
 * 页面上的格子条、右栏摘要、逐行表格和试发都用这一套说法。
 */

export const ROW_STATUS_TEXT: Record<RunRowStatus, string> = { done: '成功', failed: '调用失败', format: '格式不对', pending: '未跑' }

export interface FieldDiff { field: string; before: string; after: string }

/** 「2026-10-28 16:19:00」→「10-28 16:19」 */
export function shortTime(value: string): string {
  return value.slice(5, 16)
}

export function isProblem(row: Pick<RunRow, 'status'>): boolean {
  return row.status === 'failed' || row.status === 'format'
}

export function rowCounts(rows: RunRow[]): Record<'done' | 'failed' | 'format' | 'changed', number> {
  const count = (test: (row: RunRow) => boolean) => rows.filter(test).length
  return {
    done: count(row => row.status === 'done'),
    failed: count(row => row.status === 'failed'),
    format: count(row => row.status === 'format'),
    changed: count(row => Boolean(row.change)),
  }
}

/** 要看的行：有问题的在前，然后是和上次不同的（修好的、字段变了的），各按行号。 */
export function rowsToWatch(rows: RunRow[]): RunRow[] {
  return [...rows.filter(isProblem), ...rows.filter(row => !isProblem(row) && row.change)]
}

/**
 * 超过这么多字的值算说明文字（打标理由、解读概述）：真模型每次措辞都不一样，不算「结果变了」，
 * 免得把标签的真变化淹没。和后端 run_compare.PROSE_CHARS 一致。
 */
export const PROSE_CHARS = 40

export function isProse(...values: string[]): boolean {
  return values.some(value => value.length > PROSE_CHARS)
}

/** 两次结果的第一处不同：条数不同就说条数，否则是第一个值不同的标签类字段（说明文字措辞变了不算）。 */
export function firstDiff(after: Record<string, string>[], before: Record<string, string>[], fields: string[]): FieldDiff | null {
  if (after.length !== before.length) return { field: '条数', before: `${before.length} 条`, after: `${after.length} 条` }
  for (const [index, entry] of after.entries()) {
    const differs = (name: string) => {
      const now = entry[name] ?? ''
      const old = before[index]?.[name] ?? ''
      return now !== old && !isProse(now, old)
    }
    const field = fields.find(differs)
    if (field) return { field, before: before[index]?.[field] ?? '', after: entry[field] ?? '' }
  }
  return null
}

/** 上一次这一行的结果，写给人看。 */
export function previousText(row: RunRow): string {
  const previous = row.previous
  if (!previous || previous.status === 'pending') return ''
  if (previous.status === 'done') return '上次成功'
  return isProblem(row) && row.status === previous.status ? '上次也是' + ROW_STATUS_TEXT[previous.status] : `上次${ROW_STATUS_TEXT[previous.status]}`
}

function changeParts(compare: SampleCompare): string[] {
  const parts = compare.fields_changed ? ['两次的输出字段不同'] : []
  if (compare.fixed) parts.push(`修好 ${compare.fixed} 行`)
  if (compare.broke) parts.push(`新出问题 ${compare.broke} 行`)
  if (compare.changed) parts.push(`${compare.changed} 行字段值变了`)
  return parts
}

/** 「对比第 2 次试跑（10-28 16:02）：修好 1 行，新出问题 1 行，1 行字段值变了，其余 7 行一样。」 */
export function compareText(compare: SampleCompare | null): string {
  if (!compare) return ''
  const name = `第 ${compare.run.no} 次试跑（${shortTime(compare.run.created_at)}）`
  if (!compare.same_input) return `${name}用的测试样本和这次不同，没法逐行对比。`
  const moved = (compare.fixed ?? 0) + (compare.broke ?? 0) + (compare.changed ?? 0)
  if (!moved) return `和${name}比，跑到的行结果都一样。`
  const rest = compare.same ? `，其余 ${compare.same} 行一样` : ''
  return `对比${name}：${changeParts(compare).join('，')}${rest}。`
}

export interface RowNote { labels: { tone: string; text: string }[]; text: string }

function problemNote(row: RunRow): RowNote {
  const broke = row.change === 'broke'
  const labels: RowNote['labels'] = [{ tone: row.status, text: ROW_STATUS_TEXT[row.status] }]
  if (broke) labels.push({ tone: 'changed', text: previousText(row) })
  if (row.status === 'failed') return { labels, text: row.error }
  return { labels, text: `回答没按输出字段返回${broke ? '。上次能解析，多半和这次改的提示词有关' : ''}` }
}

/** 「要看的行」里这一行为什么要看：标签 + 一句说明。 */
export function rowNote(row: RunRow, fields: string[]): RowNote {
  if (isProblem(row)) return problemNote(row)
  if (row.change === 'fixed') return { labels: [{ tone: 'fixed', text: '修好了' }], text: `${previousText(row)}，这次解析成功` }
  const diff = row.previous ? firstDiff(row.items, row.previous.items, fields) : null
  return { labels: [{ tone: 'changed', text: '字段变了' }], text: diff ? `${diff.field}「${diff.before || '空'}」改成「${diff.after || '空'}」` : '' }
}

/** 逐行表格里一个输出字段的格子：第一条的值；标签类字段和上次不同时另给上次的值（说明文字展开一行再对照）。 */
export function fieldCell(row: RunRow, field: string): { now: string; before: string | null } {
  const now = row.items[0]?.[field] ?? ''
  if (!row.change || row.previous?.status !== 'done') return { now, before: null }
  const old = row.previous.items[0]?.[field] ?? ''
  return { now, before: old !== now && !isProse(now, old) ? old : null }
}

/** 一次回答写给人看：解析出的字段一条一段；没解析出就给失败原因和模型原话。 */
export function answerLines(entry: Pick<RunRow, 'status' | 'items' | 'error' | 'answer'>, fields: string[]): string {
  if (entry.status === 'pending') return '这次没跑到这一行'
  const parsed = entry.items.map(item => fields.map(name => `${name}：${item[name] || '—'}`).join('\n')).join('\n\n')
  return [parsed, entry.error, entry.answer].filter(Boolean).join('\n\n') || '（空）'
}

/** 批量任务跑的是哪一版：第 N 版，或者哪次保存的草稿。 */
export function versionLabel(run: Pick<BatchRun, 'release_no' | 'draft_saved_at'>): string {
  if (run.release_no !== null) return `第 ${run.release_no} 版`
  return run.draft_saved_at ? `草稿 ${shortTime(run.draft_saved_at)}` : '—'
}

/** 按最近一次样本试跑每条的平均费用估这次要花多少；没试跑过、或者没花钱的给不出。 */
/**
 * 按最近一次样本试跑的单条费用估这次任务。样本跑的不是这次要跑的内容就不估（返回 null），宁可不写也不能低估几十倍：
 * 草稿改过（如换成六级码表，每行多 3.8 万字）、深度思考开关不一样、跑上线版本而草稿和线上不一样（样本跑的是草稿）。
 */
export function estimateCost(
  sample: SampleSummary | null | undefined,
  rows: number,
  run: { thinking: boolean; draftMatchesRun: boolean } = { thinking: false, draftMatchesRun: true },
): { total: number; perRow: number } | null {
  if (!sample?.done_count || !(sample.cost > 0) || rows <= 0) return null
  if (!sample.current || !run.draftMatchesRun || Boolean(sample.thinking) !== run.thinking) return null
  const perRow = sample.cost / sample.done_count
  return { total: perRow * rows, perRow }
}

/** 逐行表格的查找：输入、输出字段、失败原因、模型原话，任何一处含关键字都算。 */
export function rowMatches(row: RunRow, keyword: string): boolean {
  const needle = keyword.trim()
  if (!needle) return true
  const texts = [...Object.values(row.inputs), ...row.items.flatMap(item => Object.values(item)), row.error, row.answer]
  return texts.some(text => text.includes(needle))
}

export interface TrialVerdict { tone: 'good' | 'bad' | 'chg' | 'same'; label: string; text: string }

/**
 * 试发一行之后，和这一行在样本试跑里的结果比：改完提示词，这一行修好了没有。
 * parsed 是试发按输出字段解析的结果，null 表示格式不对；没设输出字段时不比。
 */
export function trialVerdict(sampleRow: RunRow | undefined, parsed: Record<string, string>[] | null | undefined, sampleNo: number, fields: string[]): TrialVerdict | null {
  if (!sampleRow || sampleRow.status === 'pending' || parsed === undefined) return null
  const where = `这一行在第 ${sampleNo} 次样本试跑里`
  if (parsed === null) {
    return isProblem(sampleRow)
      ? { tone: 'bad', label: '还是不对', text: `${where}也${ROW_STATUS_TEXT[sampleRow.status]}，现在仍没按输出字段返回。` }
      : { tone: 'bad', label: '变坏了', text: `${where}是成功的，现在没按输出字段返回。` }
  }
  if (isProblem(sampleRow)) return { tone: 'good', label: '修好了', text: `${where}${ROW_STATUS_TEXT[sampleRow.status]}，用现在的提示词能解析了。` }
  const diff = firstDiff(parsed, sampleRow.items, fields)
  if (!diff) return { tone: 'same', label: '一样', text: `和${where}的结果一样。` }
  return { tone: 'chg', label: '结果变了', text: `和${where}比，${diff.field}「${diff.before || '空'}」改成「${diff.after || '空'}」。` }
}
