import { describe, expect, it } from 'vitest'

import type { ScheduledRun } from '@/api/scheduler'
import { chartPalette } from '@/components/charts/echarts'
import type { CrawlerConfigReport } from '@/api/crawlerConfig'
import { coverageOption, deltaText, headline, heatLevel, provinceBars, rangeText, sortProvinces, syncFailure, syncRunning, weekLabel, weekTitle, weeklyOption } from './report'

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

  it('图表：一周一根柱子，累计数只在提示框里', () => {
    const option = weeklyOption([week], chartPalette()) as { series: { type: string; data: number[] }[] }
    expect(option.series.map(item => [item.type, item.data])).toEqual([['bar', [4]]])
  })
})

describe('周次、分省排序和每周配置数底色', () => {
  it('ISO 周次和周选择器一致', () => {
    expect(weekTitle('2026-10-19')).toBe('2026 年第 43 周')
    expect(weekTitle('2026-12-28')).toBe('2026 年第 53 周')
    expect(weekTitle('2027-01-04')).toBe('2027 年第 1 周')
  })

  it('三种排序，没填省份的始终在最后', () => {
    const row = (province_name: string, total: number, coverage: number, added: number) => ({ province_name, total, coverage, new: added, online: 0, pending: 0, abnormal: 0, weekly: [] })
    const rows = [row('（未填省份）', 999, 0, 99), row('甲', 10, 50, 1), row('乙', 20, 80, 0), row('丙', 5, 20, 3)]
    const names = (sort: 'total' | 'new' | 'coverage') => sortProvinces(rows, sort).map(item => item.province_name)
    expect(names('total')).toEqual(['乙', '甲', '丙', '（未填省份）'])
    expect(names('new')).toEqual(['丙', '甲', '乙', '（未填省份）'])
    expect(names('coverage')).toEqual(['丙', '甲', '乙', '（未填省份）'])
  })

  it('0 不着色，最大值最深，最小的也看得出来', () => {
    expect([heatLevel(0, 10), heatLevel(10, 10), heatLevel(1, 10)]).toEqual([0, 1, 0.24])
  })
})

const counts = { total: 100, online: 60, pending: 38, abnormal: 2, new: 5, coverage: 60 }
const base: CrawlerConfigReport = {
  week_from: '2026-11-09', week_to: '2026-11-15', report_start: '2026-10-26', counted: true, baseline: 50,
  previous_new: 3, totals: counts, provinces: [{ province_name: '广东省', ...counts, weekly: [5] }],
  trend: [{ week_from: '2026-11-09', week_to: '2026-11-15', new: 5, cumulative: 58 }], new_sites: [], last_sync: null,
}
const text = (parts: { text: string }[][]) => parts.map(sentence => sentence.map(part => part.text).join('')).join('；')

describe('给领导的结论句', () => {
  it('本周：已配置、覆盖率、本周新增和较上周、异常', () => {
    expect(text(headline(base, true))).toBe('截至今天，已配置爬虫栏目 60 个，占信源栏目的 60%；本周新增 5 个，较上周 +2；有 2 个栏目异常待核对')
  })

  it('往周：已配置用那周周末的累计；统计起点之前不谈新增；没有异常不提', () => {
    expect(text(headline(base, false))).toContain('截至 11月15日，已配置爬虫栏目 58 个')
    const before = { ...base, counted: false, trend: [], totals: { ...counts, abnormal: 0 } }
    expect(text(headline(before, false))).toBe('截至 11月15日，已配置爬虫栏目 60 个；每周新增从 10月26日那周开始统计，之前配置的都算期初存量')
  })
})

describe('进度环和分省进度条', () => {
  it('进度环三段：已爬、异常、其余', () => {
    const option = coverageOption(counts, chartPalette()) as { series: { data: { name: string; value: number }[] }[] }
    expect(option.series[0]?.data.map(item => [item.name, item.value])).toEqual([['已爬', 60], ['异常', 2], ['未爬及其他', 38]])
  })

  it('进度条按栏目总数折算比例，提示写全各项数字', () => {
    const [bar] = provinceBars(base.provinces, 'total')
    expect([bar?.online, bar?.abnormal]).toEqual([60, 2])
    expect(bar?.hint).toBe('广东省：栏目 100 个，已爬 60，未爬 38，异常 2，本周新增 5')
    expect(rangeText('2026-10-19', '2026-10-25')).toBe('10月19日 – 10月25日')
  })
})
