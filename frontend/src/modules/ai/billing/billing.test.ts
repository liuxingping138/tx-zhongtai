import { describe, expect, it } from 'vitest'

import type { BillingRow } from '@/api/aiBilling'
import {
  buildLedgerCards, cachedText, colorMap, countActiveFilters, dailySeries, daysBetween, filterOptions,
  filterRows, groupBy, money, presetRange, pruneFilters, pruneInPlace, sortGroups, summarize, tokens, totalCards,
  type BillingFilters,
} from './billing'

/** owner：业务分类 + 一级业务板块，默认「测试 / 政策」 */
const row = (day: string, model: string, purpose: string, cost: string, calls = 1, owner: [string, string] = ['测试', '政策']): BillingRow =>
  ({ day, model, scene: owner[0], category: owner[1], purpose, calls, input_tokens: 1000 * calls, output_tokens: 100 * calls, cached_tokens: 400 * calls, cost })

const ROWS = [
  row('2026-10-20', '方舟Flash', '批量任务', '1.5', 2, ['测试', '客户']),
  row('2026-10-22', '方舟Flash', '政策AI打标·政策解读', '0.25', 1, ['日常调度', '政策']),
  row('2026-10-22', '千帆V3.2', '多轮对话', '0.25', 3),
]
const NONE: BillingFilters = { scenes: [], categories: [], purposes: [], models: [] }

describe('费用账单', () => {
  it('合计卡片和明细表带上缓存命中 token 与命中率，没有命中时写明', () => {
    const total = summarize(ROWS)
    const cache = totalCards(total).at(-1)
    expect(cache).toEqual({ label: '缓存命中 token', value: '2,400', note: '占输入 40%，按缓存单价计费', main: false })
    expect(totalCards({ ...total, cached_tokens: 0 }).at(-1)?.note).toBe('没有命中上下文缓存')
    expect(totalCards(total).filter(card => card.main).map(card => card.label)).toEqual(['合计费用'])
    expect(cachedText({ input_tokens: 30_000, cached_tokens: 20_000 })).toBe('2.0万（66.7%）')
    expect(cachedText({ input_tokens: 1000, cached_tokens: 0 })).toBe('0')
  })

  it('旧接口没有缓存字段时按 0 合计', () => {
    const legacy = { ...row('2026-10-22', 'm', '试发', '0.1'), cached_tokens: undefined } as unknown as BillingRow
    expect(summarize([legacy]).cached_tokens).toBe(0)
  })

  it('按模型、用途筛选后合计', () => {
    expect(summarize(filterRows(ROWS, { ...NONE, models: ['方舟Flash'] }))).toEqual({ calls: 3, input_tokens: 3000, output_tokens: 300, cached_tokens: 1200, cost: 1.75 })
    expect(filterRows(ROWS, { ...NONE, purposes: ['多轮对话'] })).toHaveLength(1)
    expect(filterRows(ROWS, NONE)).toHaveLength(3)
  })

  it('业务分类、一级、二级业务板块三级联动', () => {
    expect(filterRows(ROWS, { ...NONE, scenes: ['日常调度'] }).map(item => item.purpose)).toEqual(['政策AI打标·政策解读'])
    // 选了业务分类，一级只列这类下花过钱的；二级只列分类 × 一级下的。
    expect(filterOptions(ROWS, { ...NONE, scenes: ['日常调度'] }).categories).toEqual(['政策'])
    expect(filterOptions(ROWS, NONE).categories).toEqual(['政策', '客户', '招投标'])
    expect(filterOptions(ROWS, { ...NONE, scenes: ['测试'], categories: ['政策'] }).purposes).toEqual(['多轮对话'])
    // 上一级改了，下一级选不到的值去掉。
    const changed = pruneFilters(ROWS, { ...NONE, scenes: ['日常调度'], categories: ['客户', '政策'], purposes: ['批量任务', '政策AI打标·政策解读'] })
    expect([changed.categories, changed.purposes]).toEqual([['政策'], ['政策AI打标·政策解读']])
  })

  it('就地修剪：没变时数组引用不换，不会触发页面监听再修剪一轮（曾经死循环卡死页面）', () => {
    const filters: BillingFilters = { ...NONE, scenes: ['日常调度'], categories: ['政策'], purposes: [] }
    const before = filters.categories
    expect(pruneInPlace(ROWS, filters)).toBe(false)
    expect(filters.categories).toBe(before)
    filters.categories = ['客户', '政策']
    expect(pruneInPlace(ROWS, filters)).toBe(true)
    expect(filters.categories).toEqual(['政策'])
    expect(pruneInPlace(ROWS, filters)).toBe(false)
  })

  it('按模型、用途按费用从高到低，带占比；按日期从近到远', () => {
    expect(groupBy(ROWS, 'model').map(group => [group.name, group.cost, group.share])).toEqual([['方舟Flash', 1.75, 0.875], ['千帆V3.2', 0.25, 0.125]])
    expect(groupBy(ROWS, 'day').map(group => group.name)).toEqual(['2026-10-22', '2026-10-20'])
  })

  it('花得最多的拿第一个颜色、垫在最底下', () => {
    const colors = colorMap(ROWS, 'purpose')
    expect([...colors.keys()]).toEqual(['批量任务', '多轮对话', '政策AI打标·政策解读'])
    const { series } = dailySeries(ROWS, '2026-10-20', '2026-10-22', 'purpose', colors)
    expect(series.map(item => item.name)).toEqual(['批量任务', '多轮对话', '政策AI打标·政策解读'])
  })

  it('每天都有一格，没花钱的日子是 0；颜色跟名字走，筛选不重新上色', () => {
    const colors = colorMap(ROWS, 'model')
    const { days, series } = dailySeries(filterRows(ROWS, { ...NONE, models: ['千帆V3.2'] }), '2026-10-20', '2026-10-22', 'model', colors)
    expect(days).toEqual(['2026-10-20', '2026-10-21', '2026-10-22'])
    expect(series).toEqual([{ name: '千帆V3.2', color: colors.get('千帆V3.2'), data: [0, 0, 0.25] }])
    expect(colors.get('千帆V3.2')).toBe(colorMap(ROWS, 'model').get('千帆V3.2'))
  })

  it('快捷范围含今天；本月从 1 号起', () => {
    expect(presetRange('7', '2026-10-22')).toEqual(['2026-10-16', '2026-10-22'])
    expect(presetRange('month', '2026-10-22')).toEqual(['2026-10-01', '2026-10-22'])
    expect(daysBetween('2026-10-31', '2026-11-01')).toEqual(['2026-10-31', '2026-11-01'])
  })

  it('金额一元以上到分，不足一元留 4 位；token 上万用「万」、上亿用「亿」', () => {
    expect([money(12.345), money(1234.5), money(0.0031), money(0)]).toEqual(['¥12.35', '¥1,234.50', '¥0.0031', '¥0.00'])
    expect([tokens(9876), tokens(123456), tokens(181_765_000)]).toEqual(['9,876', '12.3万', '1.82亿'])
  })

  it('账本指标卡计算日均峰值、调度测试拆分与缓存命中率，支持按列排序与筛选计数', () => {
    const cards = buildLedgerCards(ROWS, 2)
    expect(cards.map(c => c.key)).toEqual(['cost', 'calls', 'input', 'output', 'cached'])
    expect(cards[0]?.note).toContain('日均 ¥1.00')
    expect(cards[0]?.note).toContain('峰值 10-20 (¥1.50)')
    expect(cards[1]?.note).toBe('调度 1 · 测试 5')
    expect(cards[4]?.badge).toBe('40%')
    expect(cards[4]?.progress).toBeCloseTo(0.4)
    expect(countActiveFilters({ scenes: ['测试'], categories: [], purposes: ['批量任务'], models: [] })).toBe(2)
    const groups = groupBy(ROWS, 'model')
    expect(sortGroups(groups, 'calls', 'asc').map(g => g.name)).toEqual(['方舟Flash', '千帆V3.2'])
    expect(sortGroups(groups, 'cost', 'asc').map(g => g.name)).toEqual(['千帆V3.2', '方舟Flash'])
  })
})
