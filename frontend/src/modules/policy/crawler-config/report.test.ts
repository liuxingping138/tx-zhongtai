import { describe, expect, it } from 'vitest'

import type { ScheduledRun } from '@/api/scheduler'
import { chartPalette } from '@/components/charts/echarts'
import { dayText, deltaText, rangeText, sparkHeights, syncFailure, syncRunning, trendWorthShowing, weekLabel, weekTitle, weeklyOption } from './report'

const week = (week_from: string, added: number) => ({ week_from, week_to: week_from, new: added, cumulative: 100 + added })
const run = (status: ScheduledRun['status'], error: string | null = null) => ({ status, error_message: error }) as ScheduledRun

describe('日期和周次', () => {
  it('ISO 周次和周选择器一致', () => {
    expect(weekTitle('2026-10-19')).toBe('2026 年第 43 周')
    expect(weekTitle('2026-12-28')).toBe('2026 年第 53 周')
    expect(weekTitle('2027-01-04')).toBe('2027 年第 1 周')
  })

  it('月日写法', () => {
    expect(dayText('2026-10-23')).toBe('10月23日')
    expect(rangeText('2026-10-19', '2026-10-25')).toBe('10月19日 – 10月25日')
    expect(weekLabel(week('2026-11-02', 4))).toBe('11-02')
  })
})

describe('较上周与同步状态', () => {
  it('多了绿、少了红、一样写持平', () => {
    expect(deltaText(267, 203)).toEqual({ text: '较上周 +64', tone: 'good' })
    expect(deltaText(1, 3)).toEqual({ text: '较上周 -2', tone: 'bad' })
    expect(deltaText(3, 3)).toEqual({ text: '与上周持平', tone: 'flat' })
  })

  it('在跑不提示失败，最近一次失败才提示', () => {
    expect(syncRunning({ active_run: run('queued'), last_run: null })).toBe(true)
    expect(syncRunning(null)).toBe(false)
    expect(syncFailure({ active_run: run('running'), last_run: run('failed', 'x') })).toBe('')
    expect(syncFailure({ active_run: null, last_run: run('success') })).toBe('')
    expect(syncFailure({ active_run: null, last_run: run('failed', '同步失败（OperationalError）') })).toContain('同步失败（OperationalError）')
  })
})

describe('每周配置数量图和分省小柱', () => {
  it('有数据的周不到两周就不画', () => {
    expect(trendWorthShowing([week('2026-10-12', 0), week('2026-10-19', 267)])).toBe(false)
    expect(trendWorthShowing([week('2026-10-12', 203), week('2026-10-19', 267)])).toBe(true)
  })

  it('所选那周实色，其余淡色，0 不标数字', () => {
    const option = weeklyOption([week('2026-10-12', 203), week('2026-10-19', 0)], chartPalette()) as {
      series: { data: { value: number; itemStyle: { opacity: number } }[]; label: { formatter: (item: { value: number }) => string } }[]
    }
    const [series] = option.series
    expect(series?.data.map(item => [item.value, item.itemStyle.opacity])).toEqual([[203, 0.45], [0, 1]])
    expect([series?.label.formatter({ value: 0 }), series?.label.formatter({ value: 5 })]).toEqual(['', '5'])
  })

  it('小柱按这一行最大值折算，最低也看得见，全 0 不画', () => {
    expect(sparkHeights([0, 1, 10])).toEqual([0, 10, 100])
    expect(sparkHeights([0, 0])).toEqual([0, 0])
    expect(sparkHeights([1, 100])).toEqual([8, 100])
  })
})
