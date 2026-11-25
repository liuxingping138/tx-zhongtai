/** 费用账单页的纯计算：筛选、合计、洞察账本卡、分组排序、按天序列和固定配色。 */
import type { BillingRow } from '@/api/aiBilling'
import { cacheHitText } from '../shared/aiText'

export type GroupKey = 'model' | 'purpose' | 'day'
export type SortKey = 'name' | 'calls' | 'input_tokens' | 'cached_rate' | 'output_tokens' | 'cost'
export type SortOrder = 'asc' | 'desc'

export interface BillingGroup {
  name: string
  calls: number
  input_tokens: number
  output_tokens: number
  /** 输入 token 里命中上下文缓存的部分 */
  cached_tokens: number
  cost: number
  /** 占所选范围合计费用的比例，0～1 */
  share: number
}

export interface LedgerCardItem {
  key: 'cost' | 'calls' | 'input' | 'output' | 'cached'
  label: string
  value: string
  badge?: string
  note: string
  main: boolean
  progress?: number
}

/** 分类色板（已用色盲和对比度校验）：颜色跟着模型或用途走，筛掉别的系列也不变色。超过 8 个的并进「其他」。 */
export const SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
export const DARK_SERIES_COLORS = ['#60a5fa', '#fb923c', '#34d399', '#fbbf24', '#f472b6', '#4ade80', '#a78bfa', '#f87171']
export const OTHER = '其他'
const OTHER_COLOR = '#9aa4b2'
const DARK_OTHER_COLOR = '#94a3b8'

/** 页面上的筛选。scene → category → purpose 三级联动，model 独立；空数组表示不限。 */
export interface BillingFilters {
  scenes: string[]
  categories: string[]
  purposes: string[]
  models: string[]
}

/** 业务分类固定两类，一级业务板块固定三类：没花钱的也列出来，页面上的选项不随日期范围忽有忽无。 */
export const SCENES = ['日常调度', '测试']
export const CATEGORIES = ['政策', '客户', '招投标']

const within = (picked: string[], value: string) => !picked.length || picked.includes(value)

export function cacheHitRatio(inputTokens: number, cachedTokens: number): number {
  if (!inputTokens || !cachedTokens || cachedTokens <= 0) return 0
  return Math.min(1, cachedTokens / inputTokens)
}

export function isFallbackColor(color: string | undefined): boolean {
  return !color || color === OTHER_COLOR || color === DARK_OTHER_COLOR
}

export function countActiveFilters(filters: BillingFilters): number {
  return filters.scenes.length + filters.categories.length + filters.purposes.length + filters.models.length
}

export function filterRows(rows: BillingRow[], filters: BillingFilters): BillingRow[] {
  return rows.filter(row =>
    within(filters.scenes, row.scene)
    && within(filters.categories, row.category)
    && within(filters.purposes, row.purpose)
    && within(filters.models, row.model))
}

/** 联动选项：一级业务板块只列所选业务分类下花过钱的，二级业务板块只列所选业务分类 × 一级业务板块下花过钱的。
 * 已选但不在选项里的值也保留在列表里（从任务调度「查看账单」带进来的用途，这段时间可能还没花钱）。 */
export function filterOptions(rows: BillingRow[], filters: BillingFilters): { categories: string[]; purposes: string[]; models: string[] } {
  const inScene = rows.filter(row => within(filters.scenes, row.scene))
  const inCategory = inScene.filter(row => within(filters.categories, row.category))
  const used = new Set(inScene.map(row => row.category))
  const sorted = (values: string[]) => [...new Set(values)].sort((a, b) => a.localeCompare(b, 'zh-CN'))
  return {
    categories: filters.scenes.length ? CATEGORIES.filter(name => used.has(name) || filters.categories.includes(name)) : CATEGORIES,
    purposes: sorted([...inCategory.map(row => row.purpose), ...filters.purposes]),
    models: sorted([...rows.map(row => row.model), ...filters.models]),
  }
}

/** 上一级改了以后，下一级里已经不在选项中的值去掉：不然筛选框里留着一个选不到的值，底下的数也一直是 0。 */
export function pruneFilters(rows: BillingRow[], filters: BillingFilters): BillingFilters {
  const options = filterOptions(rows, { ...filters, categories: [], purposes: [] })
  const categories = filters.categories.filter(name => options.categories.includes(name))
  const purposes = filters.purposes.filter(name => filterOptions(rows, { ...filters, categories, purposes: [] }).purposes.includes(name))
  return { ...filters, categories, purposes }
}

export function summarize(rows: BillingRow[]): Omit<BillingGroup, 'name' | 'share'> {
  return rows.reduce(
    (sum, row) => ({
      calls: sum.calls + row.calls,
      input_tokens: sum.input_tokens + row.input_tokens,
      output_tokens: sum.output_tokens + row.output_tokens,
      // 缓存列上线前的接口没有这个字段，按 0 算
      cached_tokens: sum.cached_tokens + (row.cached_tokens ?? 0),
      cost: sum.cost + Number(row.cost),
    }),
    { calls: 0, input_tokens: 0, output_tokens: 0, cached_tokens: 0, cost: 0 },
  )
}

function peakDayStats(rows: BillingRow[]): { day: string; cost: number } {
  return groupBy(rows, 'day').reduce(
    (best, item) => (item.cost > best.cost ? { day: item.name, cost: item.cost } : best),
    { day: '', cost: 0 },
  )
}

function sceneCallSplit(rows: BillingRow[]): { schedule: number; test: number } {
  return rows.reduce(
    (acc, row) => ({
      schedule: acc.schedule + (row.scene === '日常调度' ? row.calls : 0),
      test: acc.test + (row.scene === '日常调度' ? 0 : row.calls),
    }),
    { schedule: 0, test: 0 },
  )
}

function formatRatio(input: number, output: number): string {
  return output > 0 ? `${(input / output).toFixed(1)} : 1` : '—'
}

/** 一体化 5 格财务账本条：从现有明细直接算出日均/峰值、调度/测试拆分、均次消耗与输入输出比，不改后端接口。 */
export function buildLedgerCards(shownRows: BillingRow[], daysCount: number): LedgerCardItem[] {
  const total = summarize(shownRows)
  const dailyAvg = total.cost / Math.max(1, daysCount)
  const peak = peakDayStats(shownRows)
  const split = sceneCallSplit(shownRows)
  const avgInput = total.calls ? Math.round(total.input_tokens / total.calls) : 0
  const uncachedInput = Math.max(0, total.input_tokens - total.cached_tokens)
  const avgOutput = total.calls ? Math.round(total.output_tokens / total.calls) : 0
  const hitRatio = cacheHitRatio(total.input_tokens, total.cached_tokens)
  const hitText = cacheHitText(total.input_tokens, total.cached_tokens)
  const costNote = total.cost > 0 && peak.day
    ? `日均 ${money(dailyAvg)} · 峰值 ${peak.day.slice(5)}（${money(peak.cost)}）`
    : '所选周期暂无账单支出'
  const callsNote = total.calls > 0
    ? `调度 ${split.schedule.toLocaleString('zh-CN')} · 测试 ${split.test.toLocaleString('zh-CN')}`
    : '批量任务与单次请求累计'
  return [
    { key: 'cost', label: '合计费用', value: money(total.cost), note: costNote, main: true },
    { key: 'calls', label: '调用次数', value: total.calls.toLocaleString('zh-CN'), note: callsNote, main: false },
    {
      key: 'input',
      label: '输入 token',
      value: tokens(total.input_tokens),
      note: total.input_tokens > 0 ? `均次 ${tokens(avgInput)} · 新输入 ${tokens(uncachedInput)}` : '提示词与文档上下文消耗',
      main: false,
    },
    {
      key: 'output',
      label: '输出 token',
      value: tokens(total.output_tokens),
      note: total.output_tokens > 0 ? `均次 ${tokens(avgOutput)} · 输入/输出 ${formatRatio(total.input_tokens, total.output_tokens)}` : '模型结构化生成结果消耗',
      main: false,
    },
    {
      key: 'cached',
      label: '缓存命中 token',
      value: tokens(total.cached_tokens),
      badge: hitText || '0.0%',
      note: hitText ? '按缓存单价计费' : '没有命中上下文缓存',
      main: false,
      progress: hitRatio,
    },
  ]
}

/** 保留原有静态合计卡片计算签名，兼容已有调用与单元测试。 */
export function totalCards(total: Omit<BillingGroup, 'name' | 'share'>): { label: string; value: string; note: string; main: boolean }[] {
  const hit = cacheHitText(total.input_tokens, total.cached_tokens)
  return [
    { label: '合计费用', value: money(total.cost), note: '所选周期模型调用总支出', main: true },
    { label: '调用次数', value: total.calls.toLocaleString('zh-CN'), note: '批量任务与单次请求累计', main: false },
    { label: '输入 token', value: tokens(total.input_tokens), note: '提示词与文档上下文消耗', main: false },
    { label: '输出 token', value: tokens(total.output_tokens), note: '模型结构化生成结果消耗', main: false },
    { label: '缓存命中 token', value: tokens(total.cached_tokens), note: hit ? `占输入 ${hit}，按缓存单价计费` : '没有命中上下文缓存', main: false },
  ]
}

/** 明细表的缓存命中列：token 数，有命中时带上占输入的比例。 */
export function cachedText(group: Pick<BillingGroup, 'input_tokens' | 'cached_tokens'>): string {
  const hit = cacheHitText(group.input_tokens, group.cached_tokens)
  return hit ? `${tokens(group.cached_tokens)}（${hit}）` : tokens(group.cached_tokens)
}

/** 按模型 / 用途按费用从高到低；按日期从近到远。 */
export function groupBy(rows: BillingRow[], key: GroupKey): BillingGroup[] {
  const total = summarize(rows).cost
  const groups = new Map<string, BillingRow[]>()
  for (const row of rows) groups.set(row[key], [...(groups.get(row[key]) ?? []), row])
  const result = [...groups].map(([name, items]) => {
    const sum = summarize(items)
    return { name, ...sum, share: total ? sum.cost / total : 0 }
  })
  return key === 'day'
    ? result.sort((a, b) => b.name.localeCompare(a.name))
    : result.sort((a, b) => b.cost - a.cost || a.name.localeCompare(b.name, 'zh-CN'))
}

/** 明细表按列排序：支持按名称/日期、次数、输入、缓存命中率、输出、费用升降序。 */
export function sortGroups(groups: BillingGroup[], key: SortKey, order: SortOrder): BillingGroup[] {
  const factor = order === 'asc' ? 1 : -1
  return [...groups].sort((a, b) => {
    if (key === 'name') return a.name.localeCompare(b.name, 'zh-CN') * factor
    const val = (row: BillingGroup) => (key === 'cached_rate' ? cacheHitRatio(row.input_tokens, row.cached_tokens) : row[key])
    const diff = val(a) - val(b)
    if (diff !== 0) return diff * factor
    return b.cost - a.cost || a.name.localeCompare(b.name, 'zh-CN')
  })
}

/** 名字 -> 颜色，顺序也是柱子里从下往上的堆叠顺序。
 * 按全部数据（未筛选）里各自的总花费从高到低排：花得最多的拿最醒目的颜色、垫在最底下。筛选只是隐藏系列，不重新上色。 */
export function colorMap(rows: BillingRow[], key: 'model' | 'purpose', dark = false): Map<string, string> {
  const palette = dark ? DARK_SERIES_COLORS : SERIES_COLORS
  const fallback = dark ? DARK_OTHER_COLOR : OTHER_COLOR
  const names = groupBy(rows, key).map(group => group.name)
  return new Map(names.map((name, index) => [name, palette[index] ?? fallback]))
}

/** 范围内每一天（没花钱的日子补 0），每个系列一组按天的费用。 */
export function dailySeries(
  rows: BillingRow[],
  from: string,
  to: string,
  key: 'model' | 'purpose',
  colors: Map<string, string>,
  dark = false,
) {
  const fallback = dark ? DARK_OTHER_COLOR : OTHER_COLOR
  const days = daysBetween(from, to)
  const index = new Map(days.map((day, position) => [day, position]))
  const series = new Map<string, number[]>()
  for (const row of rows) {
    const name = colors.get(row[key]) === fallback ? OTHER : row[key]
    const values = series.get(name) ?? days.map(() => 0)
    const position = index.get(row.day)
    if (position !== undefined) values[position] = (values[position] ?? 0) + Number(row.cost)
    series.set(name, values)
  }
  const order = [...colors.keys(), OTHER]
  const names = [...series.keys()].sort((a, b) => order.indexOf(a) - order.indexOf(b))
  return { days, series: names.map(name => ({ name, color: colors.get(name) ?? fallback, data: series.get(name) ?? [] })) }
}

export function daysBetween(from: string, to: string): string[] {
  const days: string[] = []
  const end = Date.parse(`${to}T00:00:00Z`)
  for (let time = Date.parse(`${from}T00:00:00Z`); time <= end && days.length < 400; time += 86_400_000) {
    days.push(new Date(time).toISOString().slice(0, 10))
  }
  return days
}

export type RangePreset = '7' | '30' | '90' | 'month'

/** 快捷范围，都含今天（北京日期由调用方传入）。 */
export function presetRange(preset: RangePreset, today: string): [string, string] {
  if (preset === 'month') return [`${today.slice(0, 8)}01`, today]
  const start = new Date(Date.parse(`${today}T00:00:00Z`) - (Number(preset) - 1) * 86_400_000)
  return [start.toISOString().slice(0, 10), today]
}

/** 金额：一元以上到分（带千分位），不足一元留 4 位（试发几次常是千分之一元量级）。 */
export function money(value: number): string {
  if (Math.abs(value) >= 1 || value === 0) {
    return `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  return `¥${value.toFixed(4)}`
}

/** token 数：上亿用「亿」，上万用「万」。 */
export function tokens(value: number): string {
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(2)}亿`
  return value >= 10_000 ? `${(value / 10_000).toFixed(1)}万` : value.toLocaleString('zh-CN')
}

/** 就地修剪页面上的筛选，返回有没有改。只删不加，长度没变就是没变，这时一个数组也不换：
 * 页面监听着 categories，换成新数组（哪怕内容一样）就会再触发修剪，修剪 → 赋值 → 再修剪，死循环把页面卡死。 */
export function pruneInPlace(rows: BillingRow[], filters: BillingFilters): boolean {
  const next = pruneFilters(rows, filters)
  let changed = false
  if (next.categories.length !== filters.categories.length) {
    filters.categories = next.categories
    changed = true
  }
  if (next.purposes.length !== filters.purposes.length) {
    filters.purposes = next.purposes
    changed = true
  }
  return changed
}
