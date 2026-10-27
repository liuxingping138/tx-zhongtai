/**
 * 一行解析出多条结果（一条政策对应好几个场景）时怎么摆：各条都一样的字段只列一次，
 * 每条折叠成一行摘要（前几个不一样的字段），点开再看其余字段。只有一条时照常全列。
 */
export interface RowLayout {
  /** 各条取值都相同的字段，列在最上面一次 */
  shared: string[]
  /** 各条不一样的字段，在每条里列 */
  own: string[]
}

const SUMMARY_FIELDS = 3
/** 模型没内容时常填「-」：摘要里当空值跳过，免得写成「互联网行业一部 · - · -」 */
const BLANKS = new Set(['', '-', '—', '－'])

export function rowLayout(items: Record<string, string>[], fields: string[]): RowLayout {
  const first = items[0]
  if (items.length < 2 || !first) return { shared: [], own: fields }
  const shared = fields.filter(field => items.every(item => (item[field] ?? '') === (first[field] ?? '')))
  return { shared, own: fields.filter(field => !shared.includes(field)) }
}

export function itemSummary(item: Record<string, string>, own: string[]): string {
  return own.slice(0, SUMMARY_FIELDS).map(field => item[field]?.trim() ?? '').filter(value => !BLANKS.has(value)).join(' · ') || '和上面相同'
}
