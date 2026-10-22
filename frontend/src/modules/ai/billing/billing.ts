/** 费用账单页的纯计算：筛选、合计、分组、按天序列和固定配色。 */
import type { BillingRow } from '@/api/aiBilling'

export type GroupKey = 'model' | 'purpose' | 'day'

export interface BillingGroup {
  name: string
  calls: number
  input_tokens: number
  output_tokens: number
  cost: number
  /** 占所选范围合计费用的比例，0～1 */
  share: number
}

/** 分类色板（已用色盲和对比度校验）：颜色跟着模型或用途走，筛掉别的系列也不变色。超过 8 个的并进「其他」。 */
export const SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
export const OTHER = '其他'
const OTHER_COLOR = '#9aa4b2'

export function filterRows(rows: BillingRow[], models: string[], purposes: string[]): BillingRow[] {
  return rows.filter(row => (!models.length || models.includes(row.model)) && (!purposes.length || purposes.includes(row.purpose)))
}

export function summarize(rows: BillingRow[]): Omit<BillingGroup, 'name' | 'share'> {
  return rows.reduce(
    (sum, row) => ({
      calls: sum.calls + row.calls,
      input_tokens: sum.input_tokens + row.input_tokens,
      output_tokens: sum.output_tokens + row.output_tokens,
      cost: sum.cost + Number(row.cost),
    }),
    { calls: 0, input_tokens: 0, output_tokens: 0, cost: 0 },
  )
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

/** 名字 -> 颜色，顺序也是柱子里从下往上的堆叠顺序。
 * 按全部数据（未筛选）里各自的总花费从高到低排：花得最多的拿最醒目的颜色、垫在最底下。筛选只是隐藏系列，不重新上色。 */
export function colorMap(rows: BillingRow[], key: 'model' | 'purpose'): Map<string, string> {
  const names = groupBy(rows, key).map(group => group.name)
  return new Map(names.map((name, index) => [name, SERIES_COLORS[index] ?? OTHER_COLOR]))
}

/** 范围内每一天（没花钱的日子补 0），每个系列一组按天的费用。 */
export function dailySeries(rows: BillingRow[], from: string, to: string, key: 'model' | 'purpose', colors: Map<string, string>) {
  const days = daysBetween(from, to)
  const index = new Map(days.map((day, position) => [day, position]))
  const series = new Map<string, number[]>()
  for (const row of rows) {
    const name = colors.get(row[key]) === OTHER_COLOR ? OTHER : row[key]
    const values = series.get(name) ?? days.map(() => 0)
    const position = index.get(row.day)
    if (position !== undefined) values[position] = (values[position] ?? 0) + Number(row.cost)
    series.set(name, values)
  }
  const order = [...colors.keys(), OTHER]
  const names = [...series.keys()].sort((a, b) => order.indexOf(a) - order.indexOf(b))
  return { days, series: names.map(name => ({ name, color: colors.get(name) ?? OTHER_COLOR, data: series.get(name) ?? [] })) }
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

/** 金额：一元以上到分，不足一元留 4 位（试发几次常是千分之一元量级）。 */
export function money(value: number): string {
  return `¥${Math.abs(value) >= 1 || value === 0 ? value.toFixed(2) : value.toFixed(4)}`
}

/** token 数：上万用「万」。 */
export function tokens(value: number): string {
  return value >= 10_000 ? `${(value / 10_000).toFixed(1)}万` : value.toLocaleString('zh-CN')
}
