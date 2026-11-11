import { describe, expect, it } from 'vitest'

import type { CrawlerProvince, CrawlerTrendPoint } from '@/api/crawlerMonitoring'
import { chartPalette, useChartPalette } from '@/components/charts/echarts'
import {
  changeText,
  countText,
  headline,
  healthOption,
  healthSlices,
  isWeekend,
  percent,
  provinceRanks,
  provinceSelected,
  provinceShortName,
  provinceTile,
  rateDelta,
  siteTrendOption,
  siteTrendSummary,
  sortProvinces,
  trendBuckets,
  trendOption,
  trendSummary,
  weekDelta,
} from './charts'

const palette = chartPalette()

function point(date: string, rows: number, sites = 1): CrawlerTrendPoint {
  return { date, rows, sites }
}

function province(name: string, normal: number, watch: number, stale: number, rawNames = [name]): CrawlerProvince {
  return { name, raw_names: rawNames, normal, watch, stale, sites: normal + watch + stale }
}

type Series = { name: string; data: unknown[] }

describe('采集趋势', () => {
  it('周六周日算周末', () => {
    expect([isWeekend('2026-10-10'), isWeekend('2026-10-11'), isWeekend('2026-10-12')]).toEqual([true, true, false])
  })

  type Tooltip = { formatter: (params: { dataIndex: number }[]) => string }
  type TrendChart = { series: (Series & { type: string })[]; xAxis: { data: string[] }; yAxis: { name: string; max?: number }; tooltip: Tooltip }

  it('7 天用柱状图且周末浅色，1 个月按天画折线面积并含较均值提示', () => {
    const barOption = trendOption([point('2026-10-09', 100), point('2026-10-10', 40)], 7, palette) as {
      series: { type: string; data: { value: number; itemStyle: { color: string } }[] }[]
      tooltip: Tooltip
    }
    expect(barOption.series[0]?.type).toBe('bar')
    expect(barOption.series[0]?.data.map(bar => bar.itemStyle.color)).toEqual([palette.primary, palette.weekendBar])
    expect(barOption.tooltip.formatter([{ dataIndex: 1 }])).toBe('<b>2026-10-10（周末）</b><br/>采集 40 条')

    const option = trendOption([point('2026-07-16', 72_000), point('2026-07-17', 18_000)], 30, palette) as TrendChart
    expect(option.series[0]?.type).toBe('line')
    expect(option.series.map(series => series.name)).toEqual(['每日采集量'])
    expect(option.series[0]?.data).toEqual([72_000, 18_000])
    expect(option.yAxis.max).toBeUndefined()
    expect(option.xAxis.data).toEqual(['7/16', '7/17'])
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toBe('<b>2026-07-17</b><br/>采集 18,000 条<br/>较均值 -60%')
    expect(option.tooltip.formatter([{ dataIndex: 9 }])).toBe('')
  })

  it('1 个季度按周画日均，首尾不满一周按实际天数平均', () => {
    const points = [point('2026-10-04', 70), point('2026-10-05', 20), point('2026-10-06', 40)]
    expect(trendBuckets(points, 90)).toEqual([
      { start: '2026-09-28', label: '9/28', rows: 70, days: 1, average: 70 },
      { start: '2026-10-05', label: '10/5', rows: 60, days: 2, average: 30 },
    ])
    const option = trendOption(points, 90, palette) as TrendChart
    expect(option.series[0]?.name).toBe('每周日均采集量')
    expect(option.yAxis.name).toBe('日均条数')
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toBe('<b>2026-10-05 起一周</b><br/>日均 30 条<br/>共 60 条（2 天）')
  })

  it('1 年按月画日均', () => {
    const option = trendOption([point('2026-09-30', 10), point('2026-10-01', 4), point('2026-10-02', 8)], 365, palette) as TrendChart
    expect(option.xAxis.data).toEqual(['9月', '10月'])
    expect(option.series[0]?.data).toEqual([10, 6])
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toBe('<b>2026-10</b><br/>日均 6 条<br/>共 12 条（2 天）')
  })

  it('文字说明给出总量和日均，不报峰值', () => {
    const points = Array.from({ length: 10 }, (_, index) => point(`2026-10-${String(index + 1).padStart(2, '0')}`, index < 3 ? 100_000 : 700))
    expect(trendSummary(points, 30)).toBe('近 1 个月共采集 30.5 万条，日均 30,490 条')
    expect(trendSummary([point('2026-10-01', 7)], 7)).toBe('近 7 天共采集 7 条，日均 7 条')
    expect(trendSummary([], 90)).toBe('所选时间范围内没有采集数据')
  })
})

describe('健康结构', () => {
  const health = { normal: 50, watch: 20, stale_recent: 10, stale_long: 20, long_stale_days: 90 }
  const slices = healthSlices(health, { normal_days: 7, watch_days: 30 }, palette)

  it('停更拆成近期和长期，两者点击都筛「停更」', () => {
    expect(slices.map(slice => [slice.label, slice.value, slice.status])).toEqual([
      ['正常', 50, 'normal'],
      ['关注', 20, 'watch'],
      ['近期停更', 10, 'stale'],
      ['长期停更', 20, 'stale'],
    ])
    expect(slices[2]?.hint).toBe('31–90 天无新数据，优先排查')
  })

  it('环形图每块对应一类，选中状态时未选中扇区变淡', () => {
    const option = healthOption(slices, palette) as { series: { data: { name: string; itemStyle: { opacity: number } }[] }[] }
    expect(option.series[0]?.data.map(item => item.name)).toEqual(['正常', '关注', '近期停更', '长期停更'])
    expect(option.series[0]?.data.map(item => item.itemStyle.opacity)).toEqual([1, 1, 1, 1])

    const filtered = healthOption(slices, palette, ['normal']) as { series: { data: { itemStyle: { opacity: number } }[] }[] }
    expect(filtered.series[0]?.data.map(item => item.itemStyle.opacity)).toEqual([1, 0.22, 0.22, 0.22])
  })

  it('占比保留一位小数，总数为 0 不报错', () => {
    expect([percent(1, 3), percent(1, 0)]).toEqual(['33.3%', '0%'])
  })
})

describe('环比', () => {
  it('上升、下降、持平和前一周期为 0', () => {
    expect(changeText(120, 100)).toEqual({ text: '↑ 20.0%', trend: 'up' })
    expect(changeText(50, 100)).toEqual({ text: '↓ 50.0%', trend: 'down' })
    expect(changeText(100, 100)).toEqual({ text: '与前一周期持平', trend: 'flat' })
    expect(changeText(100, 0)).toEqual({ text: '前一周期无数据', trend: 'flat' })
  })
})

describe('一句话结论', () => {
  const overview = {
    cards: { sites: 1000, normal: 400, watch: 300, stale: 300, total_rows: 1 },
    recent: { days: 7, rows: 30_000, previous_rows: 25_000 },
    week_base: { date: '2026-10-05', sites: 1000, normal: 450, watch: 250, stale: 300 },
    health: { normal: 400, watch: 300, stale_recent: 100, stale_long: 200, long_stale_days: 90 },
    provinces: [],
    sync: { status: 'success' as const, started_at: '', last_success_at: '', outdated: false },
    thresholds: { normal_days: 7, watch_days: 30 },
  }
  const plain = (sentences: { text: string }[][]) => sentences.map(parts => parts.map(part => part.text).join(''))

  it('依次说整体健康和采集量变化', () => {
    expect(plain(headline(overview))).toEqual([
      '共监测 1,000 个网站，健康率 40.0%（较上周 ↓ 5.0 个百分点）',
      '近 7 天采集 3.0 万条，较前 7 天 ↑ 20.0%',
    ])
    const [health, volume] = headline(overview)
    expect(health?.at(-1)?.tone).toBe('bad')
    expect(volume?.at(-1)?.tone).toBe('good')
  })

  it('一周前没有记录时，不出现较上周', () => {
    expect(plain(headline({ ...overview, week_base: null, recent: { days: 7, rows: 10, previous_rows: 20 } }))).toEqual([
      '共监测 1,000 个网站，健康率 40.0%',
      '近 7 天采集 10 条，较前 7 天 ↓ 50.0%',
    ])
  })
})

describe('数量文字', () => {
  it('带万、亿时单位紧跟，小数目留空格', () => {
    expect([countText(30_000), countText(700), countText(250_000_000, '条')]).toEqual(['3.0 万条', '700 条', '2.50 亿条'])
  })

})

describe('较上周', () => {
  it('颜色按含义：正常变多是好事，停更变多是坏事', () => {
    expect(weekDelta(2172, 2100, true)).toEqual({ text: '较上周 +72', tone: 'good' })
    expect(weekDelta(2166, 2120, false)).toEqual({ text: '较上周 +46', tone: 'bad' })
    expect(weekDelta(1654, 1700, false)).toEqual({ text: '较上周 −46', tone: 'good' })
    expect(weekDelta(10, 10, true)).toEqual({ text: '与上周持平', tone: 'flat' })
  })

  it('健康率变化用百分点表达，缺数据时不显示', () => {
    expect(rateDelta(40, 100, 36, 100)).toEqual({ text: '较上周 ↑ 4.0 个百分点', tone: 'good' })
    expect(rateDelta(30, 100, 36, 100)).toEqual({ text: '较上周 ↓ 6.0 个百分点', tone: 'bad' })
    expect(rateDelta(36, 100, 360, 1000)).toEqual({ text: '与上周持平', tone: 'flat' })
    expect(rateDelta(1, 0, 1, 10)).toEqual({ text: '', tone: 'flat' })
  })
})

describe('单个网站的采集曲线', () => {
  it('说明总量、有数据的天数和最近一次', () => {
    const points = [point('2026-10-09', 3), point('2026-10-10', 0), point('2026-10-11', 0)]
    expect(siteTrendSummary(points)).toBe('近 3 天共 3 条，有数据 1 天，最近一次是 2026-10-09')
    expect(siteTrendSummary([point('2026-10-11', 0)])).toBe('近 1 天没有采集到数据')
  })

  it('画近 90 天折线面积与均值线，且带统一卡片提示框与周末标注', () => {
    const option = siteTrendOption([point('2026-10-09', 3), point('2026-10-10', 1)], palette) as {
      series: { type: string; data: number[] }[]
      tooltip: { backgroundColor: string; formatter: (params: { dataIndex: number }[]) => string }
    }
    expect(option.series[0]?.type).toBe('line')
    expect(option.series[0]?.data).toEqual([3, 1])
    expect(option.tooltip.backgroundColor).toBe(palette.surface)
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toBe('<b>2026-10-10（周末）</b><br/>采集 1 条')
    expect(option.tooltip.formatter([{ dataIndex: 9 }])).toBe('')
  })
})

describe('省份分布', () => {
  const items = [province('广东省', 800, 21, 132), province('甘肃省', 400, 39, 413), province('西藏自治区', 0, 1, 20), province('天津市', 120, 9, 11)]

  it('按网站总数从多到少排序，同数按停更数，可截断', () => {
    expect(sortProvinces(items).map(item => item.name)).toEqual(['广东省', '甘肃省', '天津市', '西藏自治区'])
    expect(sortProvinces(items, 2).map(item => item.name)).toEqual(['广东省', '甘肃省'])
    const tie = province('天津市', 800, 0, 52)
    expect(sortProvinces([tie, items[1]!]).map(item => item.name)).toEqual(['甘肃省', '天津市'])
  })

  it('横轴用简称，全国、国央企等原样', () => {
    expect(['新疆维吾尔自治区', '广西壮族自治区', '宁夏回族自治区', '西藏自治区', '内蒙古自治区', '黑龙江省', '北京市', '全国', '国央企'].map(provinceShortName))
      .toEqual(['新疆', '广西', '宁夏', '西藏', '内蒙古', '黑龙江', '北京', '全国', '国央企'])
  })

  it('双列水平排行计算比例轨、停更率与合并前写法提示', () => {
    const merged = province('新疆维吾尔自治区', 20, 5, 75, ['新疆', '新疆维吾尔族自治区'])
    const empty = province('青海省', 0, 0, 0)
    const rows = provinceRanks([merged, empty])
    expect(rows.map(row => [row.rank, row.shortName, row.okWidth, row.staleWidth, row.staleRate])).toEqual([
      [1, '新疆', 25, 75, 75],
      [2, '青海', 0, 0, 0],
    ])
    expect(rows[0]?.hint).toContain('含写法：新疆、新疆维吾尔族自治区')
    expect(rows[1]?.hint).toBe('青海省：暂无网站')
  })

  it('卡片写网站数和停更率，色条按三种状态占比，提示里列出合并前的写法', () => {
    const tile = provinceTile(province('新疆维吾尔自治区', 20, 5, 75, ['新疆', '新疆维吾尔族自治区']))
    expect(tile.caption).toBe('共 100 个 · 停更 75.0%')
    expect(tile.shares).toEqual({ normal: 20, watch: 5, stale: 75 })
    expect(tile.hint).toBe('正常 20　关注 5　停更 75\n含写法：新疆、新疆维吾尔族自治区')
  })

  it('没有网站的卡片写「暂无网站」，色条为空', () => {
    const tile = provinceTile(province('青海省', 0, 0, 0))
    expect(tile.caption).toBe('暂无网站')
    expect(tile.shares).toEqual({ normal: 0, watch: 0, stale: 0 })
  })

  it('明细按该分类全部写法筛选时卡片选中，写法顺序不影响', () => {
    const merged = province('新疆维吾尔自治区', 1, 0, 1, ['新疆', '新疆维吾尔自治区'])
    expect(provinceSelected(merged, ['新疆维吾尔自治区', '新疆'])).toBe(true)
    expect(provinceSelected(merged, ['新疆'])).toBe(false)
    expect(provinceSelected(merged, [])).toBe(false)
  })
})

describe('图表配色', () => {
  it('读主题变量，读不到时用默认色，并支持响应式主题调色盘', () => {
    const style = { getPropertyValue: (name: string) => (name === '--zt-blue-600' ? ' #123456 ' : '') }
    const colors = chartPalette(style)
    expect(colors.primary).toBe('#123456')
    expect(colors.danger).toBe('#cc584b')
    const reactivePalette = useChartPalette()
    expect(reactivePalette.value.primary).toBeTruthy()
  })
})
