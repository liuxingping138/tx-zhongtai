import { describe, expect, it } from 'vitest'
import { chartPalette } from '@/components/charts/echarts'
import { isolatedHtml } from './content'
import { initialQuery, tenderColumns } from './fields'
import { recentRange, statisticsChart } from './statistics'

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
})
