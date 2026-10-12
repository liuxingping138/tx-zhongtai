import { describe, expect, it } from 'vitest'

import type { CrawlerProvince, CrawlerTrendPoint } from '@/api/crawlerMonitoringV2'
import { chartPalette } from '@/components/charts/echarts'
import {
  changeText,
  healthOption,
  healthSlices,
  isWeekend,
  movingAverage,
  percent,
  provinceOption,
  sortProvinces,
  trendOption,
  trendSummary,
  weeklyPoints,
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

  it('移动平均凑满窗口才出值', () => {
    expect(movingAverage([1, 2, 3, 4], 3)).toEqual([null, null, 2, 3])
  })

  it('按周汇总以周一为起点，条数求和、网站数取日均', () => {
    const points = [point('2026-10-04', 1, 10), point('2026-10-05', 2, 4), point('2026-10-06', 3, 6)]
    expect(weeklyPoints(points)).toEqual([
      { date: '2026-09-28', rows: 1, sites: 10 },
      { date: '2026-10-05', rows: 5, sites: 5 },
    ])
  })

  it('按天时有采集量、7 日均值、出数网站三条，周末柱子用浅色', () => {
    const option = trendOption([point('2026-10-09', 10), point('2026-10-10', 2)], 30, palette) as { series: Series[] }
    expect(option.series.map(series => series.name)).toEqual(['每日采集量', '7 日均值', '出数网站'])
    const bars = option.series[0]?.data as { itemStyle: { color: string } }[]
    expect(bars.map(bar => bar.itemStyle.color)).toEqual([palette.primary, palette.primaryLight])
  })

  it('一年按周画，不画 7 日均值', () => {
    const option = trendOption([point('2026-10-05', 1), point('2026-10-06', 2)], 365, palette) as { series: Series[]; xAxis: { data: string[] } }
    expect(option.series.map(series => series.name)).toEqual(['每周采集量', '日均出数网站'])
    expect(option.xAxis.data).toEqual(['10-05 周'])
  })

  it('文字说明给出总量和峰值，没有数据时明说', () => {
    expect(trendSummary([point('2026-10-09', 1200), point('2026-10-10', 300)], 30)).toBe('近 30 天共采集 1,500 条，最高的一天是 2026-10-09，1,200 条')
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

  it('环形图每块对应一类', () => {
    const option = healthOption(slices) as { series: { data: { name: string }[] }[] }
    expect(option.series[0]?.data.map(item => item.name)).toEqual(['正常', '关注', '近期停更', '长期停更'])
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

describe('省份分布', () => {
  const items = [province('广东省', 800, 21, 132), province('甘肃省', 400, 39, 413), province('西藏自治区', 0, 1, 20), province('天津市', 120, 9, 11)]

  it('按停更数、网站数排序并截断', () => {
    expect(sortProvinces(items, 'stale', 2).map(item => item.name)).toEqual(['甘肃省', '广东省'])
    expect(sortProvinces(items, 'sites').map(item => item.name)).toEqual(['广东省', '甘肃省', '天津市', '西藏自治区'])
  })

  it('按停更率排序时，网站太少的省份不参与', () => {
    const small = province('澳门特别行政区', 0, 0, 3)
    expect(sortProvinces([...items, small], 'rate').map(item => item.name)).toEqual(['西藏自治区', '甘肃省', '广东省', '天津市'])
  })

  it('条形图把第一名画在最上面，提示里列出合并前的写法', () => {
    const merged = province('新疆维吾尔自治区', 1, 0, 76, ['新疆', '新疆维吾尔族自治区'])
    const option = provinceOption([merged, items[0]!], palette) as {
      yAxis: { data: string[] }
      tooltip: { formatter: (params: { dataIndex: number }[]) => string }
    }
    expect(option.yAxis.data).toEqual(['广东省', '新疆维吾尔自治区'])
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toContain('含写法：新疆、新疆维吾尔族自治区')
    expect(option.tooltip.formatter([{ dataIndex: 9 }])).toBe('')
  })
})

describe('图表配色', () => {
  it('读主题变量，读不到时用默认色', () => {
    const style = { getPropertyValue: (name: string) => (name === '--zt-blue-600' ? ' #123456 ' : '') }
    const colors = chartPalette(style)
    expect(colors.primary).toBe('#123456')
    expect(colors.danger).toBe('#f56c6c')
  })
})
