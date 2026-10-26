import { describe, expect, it } from 'vitest'

import type { ScheduledRun } from '@/api/scheduler'
import { chartPalette } from '@/components/charts/echarts'
import {
  deltaText, periodLabel, periodName, periodOption, periodRange, provinceOption, provinceTableText, statusOption, statusRows, syncFailure, syncRunning, tint,
} from './report'

const run = (status: ScheduledRun['status'], error: string | null = null) => ({ status, error_message: error }) as ScheduledRun
const weeks = [
  { period_from: '2026-10-12', period_to: '2026-10-18', new: 203 },
  { period_from: '2026-10-19', period_to: '2026-10-25', new: 267 },
  { period_from: '2026-10-26', period_to: '2026-11-01', new: 0 },
]

describe('每一期怎么写', () => {
  it('横轴写法：周写周一，月写几月（1 月带年），季度、年简写', () => {
    expect(periodLabel('week', '2026-10-19')).toBe('10/19')
    expect([periodLabel('month', '2026-10-01'), periodLabel('month', '2027-01-01')]).toEqual(['10月', '2027年1月'])
    expect(periodLabel('quarter', '2026-10-01')).toBe('26Q4')
    expect(periodLabel('year', '2026-01-01')).toBe('2026')
  })

  it('完整写法', () => {
    expect(periodRange('week', '2026-10-19', '2026-10-25')).toBe('10月19日 – 10月25日')
    expect(periodRange('month', '2026-10-01', '2026-10-31')).toBe('2026年10月')
    expect(periodRange('quarter', '2026-07-01', '2026-09-30')).toBe('2026年第3季度')
    expect(periodRange('year', '2026-01-01', '2026-12-31')).toBe('2026年')
  })

  it('当前这期叫本周，前一期叫上周，更早的写日期', () => {
    const base = { unit: 'week' as const, current_from: '2026-10-26', periods: weeks }
    expect(periodName({ ...base, period_from: '2026-10-26', period_to: '2026-11-01' })).toBe('本周')
    expect(periodName({ ...base, period_from: '2026-10-19', period_to: '2026-10-25' })).toBe('上周')
    expect(periodName({ ...base, period_from: '2026-10-12', period_to: '2026-10-18' })).toBe('10月12日 – 10月18日')
    expect(periodName({ unit: 'month', current_from: '2026-10-01', periods: [], period_from: '2026-10-01', period_to: '2026-10-31' })).toBe('本月')
  })
})

describe('较上一期与同步状态', () => {
  it('多了绿、少了红、一样写持平，按粒度说上一周 / 上一月', () => {
    expect(deltaText(267, 203, 'week')).toEqual({ text: '较上一周 +64', tone: 'good' })
    expect(deltaText(1, 3, 'month')).toEqual({ text: '较上一月 −2', tone: 'bad' })
    expect(deltaText(3, 3, 'quarter')).toEqual({ text: '与上一季度持平', tone: 'flat' })
  })

  it('在跑不提示失败，最近一次失败才提示', () => {
    expect(syncRunning({ active_run: run('queued'), last_run: null })).toBe(true)
    expect(syncRunning(null)).toBe(false)
    expect(syncFailure({ active_run: run('running'), last_run: run('failed', 'x') })).toBe('')
    expect(syncFailure({ active_run: null, last_run: run('success') })).toBe('')
    expect(syncFailure({ active_run: null, last_run: run('failed', '同步失败（OperationalError）') })).toContain('同步失败（OperationalError）')
  })
})

describe('配置数量图和汇报表', () => {
  it('所选那期实色、其余同色淡化，0 不标数字', () => {
    const palette = chartPalette()
    const option = periodOption('week', weeks, '2026-10-19', palette) as {
      series: { data: { value: number; itemStyle: { color: string } }[]; label: { formatter: (item: { value: number }) => string } }[]
      tooltip: { formatter: (params: { dataIndex: number }[]) => string }
    }
    const [series] = option.series
    const faded = tint(palette.primary, 0.35)
    expect(series?.data.map(item => item.itemStyle.color)).toEqual([faded, palette.primary, faded])
    expect([tint('#2c68bb', 0.35), tint('var(--x)', 0.5)]).toEqual(['rgba(44, 104, 187, 0.35)', 'var(--x)'])
    expect([series?.label.formatter({ value: 0 }), series?.label.formatter({ value: 5 })]).toEqual(['', '5'])
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toContain('10月19日 – 10月25日</b><br/>配置 267 个网站')
    expect(option.tooltip.formatter([{ dataIndex: 9 }])).toBe('')
  })

  it('各省竖柱：从多到少，横轴简称竖排、提示框写全称', () => {
    type Option = {
      xAxis: { data: string[]; axisLabel: { formatter: (name: string) => string } }
      tooltip: { formatter: (params: { dataIndex: number }[]) => string }
      series: { label: { formatter: (item: { value: number }) => string } }[]
    }
    const option = provinceOption([{ province_name: '浙江省', new: 66 }, { province_name: '内蒙古自治区', new: 43 }], chartPalette()) as Option
    expect(option.xAxis.data).toEqual(['浙江', '内蒙古'])
    expect(option.xAxis.axisLabel.formatter('浙江')).toBe('浙\n江')
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toContain('<b>内蒙古自治区</b><br/>配置 43 个网站')
    expect(option.tooltip.formatter([])).toBe('')
    expect(option.series[0]?.label.formatter({ value: 1200 })).toBe('1,200')
  })

  it('分省爬虫状态按总数排、未填省份垫底，三段叠成一根柱', () => {
    const rows = statusRows([
      { province_name: '（未填省份）', total: 900, online: 0, pending: 900, abnormal: 0 },
      { province_name: '北京市', total: 10, online: 6, pending: 3, abnormal: 1 },
      { province_name: '广东省', total: 20, online: 5, pending: 15, abnormal: 0 },
    ])
    expect(rows.map(row => row.province_name)).toEqual(['广东省', '北京市', '（未填省份）'])
    const option = statusOption(rows, chartPalette()) as {
      xAxis: { data: string[] }
      series: { name: string; stack: string; data: number[]; label: { show: boolean; formatter?: (params: { dataIndex: number }) => string } }[]
      tooltip: { formatter: (params: { dataIndex: number }[]) => string }
    }
    expect(option.xAxis.data.slice(0, 2)).toEqual(['广东', '北京'])
    expect(option.series.map(series => [series.name, series.data[1]])).toEqual([['已爬', 6], ['异常', 1], ['未爬', 3]])
    expect(option.series.map(series => series.label.show)).toEqual([false, false, true])
    expect(option.series[2]?.label.formatter?.({ dataIndex: 0 })).toBe('5')
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toContain('覆盖率 60.0%')
    expect(option.tooltip.formatter([])).toBe('')
  })

  it('复制出来就是「省份 / 配置网站数量 / 总计」，制表符分列', () => {
    expect(provinceTableText([{ province_name: '浙江省', new: 66 }, { province_name: '全国', new: 3 }], 69))
      .toBe('省份\t配置网站数量\n浙江省\t66\n全国\t3\n总计\t69')
  })
})
