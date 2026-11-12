import { describe, expect, it } from 'vitest'
import { chartPalette } from '@/components/charts/echarts'
import { isolatedHtml } from './content'
import { initialQuery, tenderColumns } from './fields'
import { recentRange, statisticsChart, compactCount, shortProvinceName, structureDonutOption } from './statistics'

describe('招中标页面规则', () => {
  it('两种列表包含各自 Excel 字段且不带大正文', () => {
    expect(tenderColumns('winbid').map(column => column.prop)).toContain('accepted_amount')
    expect(tenderColumns('purchaser').map(column => column.prop)).toContain('open_date')
    expect(tenderColumns('purchaser').map(column => column.prop)).not.toContain('content')
    expect(initialQuery().project_status).toBe('0')
  })
  it('默认日期按北京时间跨日计算', () => {
    expect(recentRange(new Date('2026-11-11T18:00:00Z'))).toEqual(['2026-11-06', '2026-11-12'])
  })
  it('原文保留排版并禁止脚本及外部网络', () => {
    const html = isolatedHtml('<table><tr><td>正文</td></tr></table>')
    expect(html).toContain('<table>')
    expect(html).toContain("default-src 'none'")
    expect(html).toContain("form-action 'none'")
    expect(html.indexOf('Content-Security-Policy')).toBeLessThan(html.indexOf('<table>'))
  })
  it('相同工作量用并列柱展示避免折线重叠', () => {
    const option = statisticsChart([{ date: '2026-11-12', purchaser: 10, winbid: 5, tagged: 3, enriched: 3, scenario: 0 }], chartPalette(), 'work')
    expect(option.series).toHaveLength(3)
    expect(option.series).toEqual([
      expect.objectContaining({ data: [3] }), expect.objectContaining({ data: [3] }), expect.objectContaining({ data: [0] }),
    ])
  })
  it('大数压缩、省份简称与结构环形图生成正确', () => {
    expect(compactCount(999)).toBe('999')
    expect(compactCount(47_352_244)).toBe('4735.2万')
    expect(compactCount(123_456_789)).toBe('1.23亿')
    expect(shortProvinceName('新疆维吾尔自治区')).toBe('新疆')
    expect(shortProvinceName('广东省')).toBe('广东')
    expect(recentRange(new Date('2026-11-11T18:00:00Z'), 14)).toEqual(['2026-10-30', '2026-11-12'])
    const donut = structureDonutOption(200, 100, chartPalette())
    expect(donut.series).toHaveLength(1)
  })
  it('接入趋势支持折线面积模式、空数据及 Y 轴万级缩写', () => {
    const palette = chartPalette()
    const lineOpt = statisticsChart(
      [{ date: '2026-11-12', purchaser: 12000, winbid: 8000, tagged: 0, enriched: 0, scenario: 0 }],
      palette,
      'intake',
      'line',
    )
    expect(lineOpt.series).toHaveLength(2)
    const emptyOpt = statisticsChart([], palette, 'intake', 'bar')
    expect(emptyOpt.series).toHaveLength(2)
    const formatter = (lineOpt.yAxis as { axisLabel: { formatter: (v: number) => string } }).axisLabel.formatter
    expect(formatter(20_000)).toBe('2万')
    expect(formatter(15_000)).toBe('1.5万')
    expect(formatter(500)).toBe('500')
  })
})
