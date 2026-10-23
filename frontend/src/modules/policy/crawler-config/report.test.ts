import { describe, expect, it } from 'vitest'

import type { ScheduledRun } from '@/api/scheduler'
import { chartPalette } from '@/components/charts/echarts'
import { deltaText, syncFailure, syncRunning, weekLabel, weeklyOption } from './report'

const week = { week_from: '2026-11-02', week_to: '2026-11-08', new: 4, cumulative: 109 }
const run = (status: ScheduledRun['status'], error: string | null = null) => ({ status, error_message: error }) as ScheduledRun

describe('crawler config report helpers', () => {
  it('周写成月日起止', () => {
    expect(weekLabel(week)).toBe('11-02 至 11-08')
  })

  it('较上周：多了绿、少了红、一样写持平，上周不在范围不比', () => {
    expect(deltaText(5, 3)).toEqual({ text: '较上周 +2', tone: 'good' })
    expect(deltaText(1, 3)).toEqual({ text: '较上周 -2', tone: 'bad' })
    expect(deltaText(3, 3)).toEqual({ text: '与上周持平', tone: 'flat' })
    expect(deltaText(3, null)).toBeNull()
  })

  it('同步状态：在跑不提示失败，最近一次失败才提示', () => {
    expect(syncRunning({ active_run: run('queued'), last_run: null })).toBe(true)
    expect(syncRunning(null)).toBe(false)
    expect(syncFailure({ active_run: run('running'), last_run: run('failed', 'x') })).toBe('')
    expect(syncFailure({ active_run: null, last_run: run('success') })).toBe('')
    expect(syncFailure({ active_run: null, last_run: run('failed', '同步失败（OperationalError）') })).toContain('同步失败（OperationalError）')
  })

  it('图表：新增是柱、累计是线，各用一个纵轴', () => {
    const option = weeklyOption([week], chartPalette()) as { series: { type: string; data: number[]; yAxisIndex?: number }[] }
    expect(option.series.map(item => [item.type, item.data, item.yAxisIndex ?? 0])).toEqual([['bar', [4], 0], ['line', [109], 1]])
  })
})
