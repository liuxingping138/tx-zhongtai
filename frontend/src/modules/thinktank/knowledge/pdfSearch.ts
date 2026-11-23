/** PDF 页内查找的纯计算：把一页的文字块拼成整页文本找匹配，再把匹配换算回各个文字块里的位置（供文字层高亮）。 */

/** 一处匹配在整页文本里的位置（左闭右开）。 */
export interface PageMatch {
  start: number
  end: number
}

/** 一处匹配落在某个文字块里的那一段（左闭右开）。 */
export interface ItemRange {
  item: number
  from: number
  to: number
}

/** 一页的文字块，与 PDF.js TextLayer 的 textDivs / textContentItemsStr 一一对应。 */
export interface PageText {
  items: string[]
  /** 各块在整页文本里的起点。 */
  starts: number[]
  text: string
}

/** 查找时不区分大小写、全角半角空白都按一个普通空格：中文 PDF 常把一行拆成好几块，拼起来再找才能跨块命中。 */
export function normalizeText(value: string): string {
  return value.replace(/\s/g, ' ').toLowerCase()
}

export function normalizeQuery(query: string): string {
  return normalizeText(query.trim())
}

/** 文字块直接首尾相接拼成整页文本（中文换行不该插空格）；块之间的位置偏移记在 starts 里。 */
export function buildPageText(items: readonly string[]): PageText {
  const starts: number[] = []
  let text = ''
  for (const str of items) {
    starts.push(text.length)
    // toLowerCase 个别字符会改变长度（如 İ）：那样的块按原文找，位置才对得上
    const lowered = normalizeText(str)
    text += lowered.length === str.length ? lowered : str
  }
  return { items: [...items], starts, text }
}

/** 整页文本里所有不重叠的匹配。query 需先经 normalizeQuery。 */
export function findInPage(page: PageText, query: string): PageMatch[] {
  if (!query) return []
  const out: PageMatch[] = []
  let at = page.text.indexOf(query)
  while (at !== -1) {
    out.push({ start: at, end: at + query.length })
    at = page.text.indexOf(query, at + query.length)
  }
  return out
}

/** 某个整页偏移落在哪个文字块：starts 递增，二分找最后一个 ≤ offset 的块。 */
function itemAt(starts: readonly number[], offset: number): number {
  let lo = 0
  let hi = starts.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (starts[mid]! <= offset) lo = mid
    else hi = mid - 1
  }
  return lo
}

/** 一处匹配拆成各文字块里的片段：跨块的匹配每块高亮自己那一截，空块跳过。 */
export function toItemRanges(page: PageText, match: PageMatch): ItemRange[] {
  if (!page.items.length || match.end <= match.start) return []
  const out: ItemRange[] = []
  for (let item = itemAt(page.starts, match.start); item < page.items.length; item += 1) {
    const begin = page.starts[item]!
    if (begin >= match.end) break
    const length = page.items[item]!.length
    const from = Math.max(match.start - begin, 0)
    const to = Math.min(match.end - begin, length)
    if (to > from) out.push({ item, from, to })
  }
  return out
}

/** 一个文字块里要高亮的若干段（已按起点排好、互不重叠），selected 是当前那处。 */
export interface Segment {
  from: number
  to: number
  selected: boolean
}

/** 本页所有匹配按文字块分组；selectedIndex 是本页第几处为当前匹配（-1 表示当前匹配不在本页）。 */
export function segmentsByItem(page: PageText, matches: readonly PageMatch[], selectedIndex: number): Map<number, Segment[]> {
  const out = new Map<number, Segment[]>()
  matches.forEach((match, index) => {
    for (const range of toItemRanges(page, match)) {
      const list = out.get(range.item) ?? []
      list.push({ from: range.from, to: range.to, selected: index === selectedIndex })
      out.set(range.item, list)
    }
  })
  return out
}

/** 一段文字按高亮段切开：[文字, 段] 交替，段为 null 表示普通文字。 */
export function splitBySegments(text: string, segments: readonly Segment[]): Array<[string, Segment | null]> {
  const out: Array<[string, Segment | null]> = []
  let at = 0
  for (const segment of segments) {
    if (segment.from > at) out.push([text.slice(at, segment.from), null])
    out.push([text.slice(segment.from, segment.to), segment])
    at = segment.to
  }
  if (at < text.length) out.push([text.slice(at), null])
  return out
}

/** 进度文字：「第 X / Y 处」；还在往后找时 Y 后面带「+」。 */
export function matchLabel(current: number, total: number, scanning: boolean): string {
  if (total === 0) return scanning ? '正在查找…' : '无匹配'
  return `第 ${current + 1} / ${total}${scanning ? '+' : ''} 处`
}
