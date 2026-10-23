import { describe, expect, it } from 'vitest'

import type { ConfigProvince } from '@/api/crawlerConfig'
import type { ScheduledRun } from '@/api/scheduler'
import { chartPalette } from '@/components/charts/echarts'
import {
  coverageOption, dayText, deltaText, heatLevel, rangeText, syncFailure, syncRunning, weekLabel, weekProvinces, weekTitle, weeklyOption,
} from './report'

const week = { week_from: '2026-11-02', week_to: '2026-11-08', new: 4, cumulative: 109 }
const run = (status: ScheduledRun['status'], error: string | null = null) => ({ status, error_message: error }) as ScheduledRun
const province = (province_name: string, added: number): ConfigProvince =>
  ({ province_name, new: added, total: 10, online: 5, pending: 5, abnormal: 0, coverage: 50, weekly: [] })

describe('日期和周次', () => {
  it('ISO 周次和周选择器一致', () => {
    expect(weekTitle('2026-10-19')).toBe('2026 年第 43 周')
    expect(weekTitle('2026-12-28')).toBe('2026 年第 53 周')
    expect(weekTitle('2027-01-04')).toBe('2027 年第 1 周')
  })

  it('月日写法', () => {
    expect(dayText('2026-10-23')).toBe('10月23日')
    expect(rangeText('2026-10-19', '2026-10-25')).toBe('10月19日 – 10月25日')
    expect(weekLabel(week)).toBe('11-02 至 11-08')
  })
})

describe('本周各省配置网站数量', () => {
  it('只列有配置的省，按数量从多到少，条长按最多的省折算', () => {
    const rows = weekProvinces([province('广东省', 5), province('浙江省', 66), province('湖北省', 0), province('辽宁省', 33)])
    expect(rows).toEqual([
      { name: '浙江省', count: 66, share: 100 },
      { name: '辽宁省', count: 33, share: 50 },
      { name: '广东省', count: 5, share: (5 * 100) / 66 },
    ])
    expect(weekProvinces([province('湖北省', 0)])).toEqual([])
  })

  it('较上周：多了绿、少了红、一样写持平，上周不在范围不比', () => {
    expect(deltaText(5, 3)).toEqual({ text: '较上周 +2', tone: 'good' })
    expect(deltaText(1, 3)).toEqual({ text: '较上周 -2', tone: 'bad' })
    expect(deltaText(3, 3)).toEqual({ text: '与上周持平', tone: 'flat' })
    expect(deltaText(3, null)).toBeNull()
  })
})

describe('同步状态', () => {
  it('在跑不提示失败，最近一次失败才提示', () => {
    expect(syncRunning({ active_run: run('queued'), last_run: null })).toBe(true)
    expect(syncRunning(null)).toBe(false)
    expect(syncFailure({ active_run: run('running'), last_run: run('failed', 'x') })).toBe('')
    expect(syncFailure({ active_run: null, last_run: run('success') })).toBe('')
    expect(syncFailure({ active_run: null, last_run: run('failed', '同步失败（OperationalError）') })).toContain('同步失败（OperationalError）')
  })
})

describe('图表', () => {
  it('每周一根柱子，累计数只在提示框里', () => {
    const option = weeklyOption([week], chartPalette()) as { series: { type: string; data: number[] }[] }
    expect(option.series.map(item => [item.type, item.data])).toEqual([['bar', [4]]])
  })

  it('进度环三段：已配置、异常、未配置', () => {
    const totals = { total: 100, online: 60, pending: 38, abnormal: 2, new: 5, coverage: 60 }
    const option = coverageOption(totals, chartPalette()) as { series: { data: { name: string; value: number }[] }[] }
    expect(option.series[0]?.data.map(item => [item.name, item.value])).toEqual([['已配置', 60], ['异常', 2], ['未配置', 38]])
  })

  it('每周配置数底色：0 不着色，最大值最深，最小的也看得出来', () => {
    expect([heatLevel(0, 10), heatLevel(10, 10), heatLevel(1, 10)]).toEqual([0, 1, 0.24])
  })
})
