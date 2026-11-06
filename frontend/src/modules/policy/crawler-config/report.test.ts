import { describe, expect, it } from 'vitest'

import type { ScheduledRun } from '@/api/scheduler'
import { chartPalette } from '@/components/charts/echarts'
import {
  adjacentPeriods, deltaText, periodLabel, periodName, periodOption, periodRange, provinceRanking, provinceTableText, statusOption, statusRows, syncFailure, syncRunning, tint,
} from './report'

const run = (status: ScheduledRun['status'], error: string | null = null) => ({ status, error_message: error }) as ScheduledRun
const weeks = [
  { period_from: '2026-10-12', period_to: '2026-10-18', new: 203 },
  { period_from: '2026-10-19', period_to: '2026-10-25', new: 267 },
  { period_from: '2026-10-26', period_to: '2026-11-01', new: 0 },
]

describe('每一期怎么写', () => {
  it('横轴写法：周写周一，月写几月，季度写第几季度，年简写', () => {
    expect(periodLabel('week', '2026-10-19')).toBe('10/19')
    expect([periodLabel('month', '2026-10-01'), periodLabel('month', '2027-01-01')]).toEqual(['10月', '1月'])
    expect(['2026-01-01', '2026-04-01', '2026-07-01', '2026-10-01'].map(day => periodLabel('quarter', day))).toEqual(['第一季度', '第二季度', '第三季度', '第四季度'])
    expect(periodLabel('year', '2026-01-01')).toBe('2026')
  })

  it('完整写法', () => {
    expect(periodRange('week', '2026-10-19', '2026-10-25')).toBe('10月19日 – 10月25日')
    expect(periodRange('month', '2026-10-01', '2026-10-31')).toBe('2026年10月')
    expect(periodRange('quarter', '2026-07-01', '2026-09-30')).toBe('2026年第三季度')
    expect(periodRange('year', '2026-01-01', '2026-12-31')).toBe('2026年')
  })

  it('当前这期叫本周，前一期叫上周，更早的写日期', () => {
    const base = { unit: 'week' as const, current_from: '2026-10-26', periods: weeks }
    expect(periodName({ ...base, period_from: '2026-10-26', period_to: '2026-11-01' })).toBe('本周')
    expect(periodName({ ...base, period_from: '2026-10-19', period_to: '2026-10-25' })).toBe('上周')
    expect(periodName({ ...base, period_from: '2026-10-12', period_to: '2026-10-18' })).toBe('10月12日 – 10月18日')
    expect(periodName({ unit: 'month', current_from: '2026-10-01', periods: [], period_from: '2026-10-01', period_to: '2026-10-31' })).toBe('本月')
  })

  it('月、季度画全年时，上一期按当前这期的位置找，不是倒数第二根', () => {
    const quarters = ['01', '04', '07', '10'].map(month => ({ period_from: `2026-${month}-01`, period_to: '', new: 0 }))
    const base = { unit: 'quarter' as const, current_from: '2026-07-01', periods: quarters, period_to: '' }
    expect(periodName({ ...base, period_from: '2026-04-01' })).toBe('上季度')
    expect(periodName({ ...base, period_from: '2026-10-01' })).toBe('2026年第四季度')
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
    const option = periodOption('week', weeks, '2026-10-19', '2026-10-26', palette) as {
      series: { data: { value: number; itemStyle: { color: string } }[]; label: { formatter: (item: { value: number }) => string } }[]
      tooltip: { formatter: (params: { dataIndex: number }[]) => string }
    }
    const [series] = option.series
    const faded = tint(palette.primary, 0.35)
    expect(series?.data.map(item => item.itemStyle.color)).toEqual([faded, palette.primary, faded])
    expect([tint('#2c68bb', 0.35), tint('#35d', 0.06), tint('var(--x)', 0.5)]).toEqual([
      'rgba(44, 104, 187, 0.35)',
      'rgba(51, 85, 221, 0.06)',
      'var(--x)',
    ])
    expect([series?.label.formatter({ value: 0 }), series?.label.formatter({ value: 5 })]).toEqual(['', '5'])
    expect(option.tooltip.formatter([{ dataIndex: 1 }])).toContain('10月19日 – 10月25日</b><br/>配置 267 个网站')
    expect(option.tooltip.formatter([{ dataIndex: 9 }])).toBe('')
  })

  it('各省排行：名次、占这期总数的比例，横条以最多的省为满格', () => {
    const rows = provinceRanking([{ province_name: '浙江省', new: 60 }, { province_name: '全国', new: 1 }], 80)
    expect(rows.map(row => [row.rank, row.share, row.width])).toEqual([[1, '75.0%', '100%'], [2, '1.3%', '2%']])
    expect(provinceRanking([], 0)).toEqual([])
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

describe('adjacentPeriods', () => {
  const periods = [
    { period_from: '2026-10-12', period_to: '2026-10-18', new: 1 },
    { period_from: '2026-10-19', period_to: '2026-10-25', new: 2 },
    { period_from: '2026-10-26', period_to: '2026-11-01', new: 3 },
  ]

  it('按正在看的期找前后：默认看上周时，上一周是上上周、下一周是本周', () => {
    const around = adjacentPeriods({ periods, period_from: '2026-10-19', current_from: '2026-10-26' })
    expect([around.previous?.period_from, around.next?.period_from]).toEqual(['2026-10-12', '2026-10-26'])
  })

  it('本期之后没到的期不能选，最早一期没有上一期', () => {
    expect(adjacentPeriods({ periods, period_from: '2026-10-19', current_from: '2026-10-19' }).next).toBeUndefined()
    expect(adjacentPeriods({ periods, period_from: '2026-10-12', current_from: '2026-10-26' }).previous).toBeUndefined()
  })
})
