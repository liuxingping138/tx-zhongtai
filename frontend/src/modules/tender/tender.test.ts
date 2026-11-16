import { describe, expect, it } from 'vitest'
import { chartPalette } from '@/components/charts/echarts'
import { isolatedHtml } from './content'
import { buildDetailSections, SYSTEM_SECTION } from '@/components/detailSections'
import { applyDefaultDateRange, initialQuery, recentDaysRange, tenderColumns, tenderDetailGroups, validateTenderSearch } from './fields'
import { buildProvinceRows, recentRange, statisticsChart, compactCount, shortProvinceName, structureDonutOption } from './statistics'

describe('招中标页面规则', () => {
  it('两种列表包含各自 Excel 字段且不带大正文', () => {
    expect(tenderColumns('winbid').map(column => column.prop)).toContain('accepted_amount')
    expect(tenderColumns('purchaser').map(column => column.prop)).toContain('open_date')
    expect(tenderColumns('purchaser').map(column => column.prop)).not.toContain('content')
    expect(initialQuery().project_status).toBe('1')
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
    const donut = structureDonutOption(200, 100, 20, 10, chartPalette())
    expect(donut.series).toHaveLength(1)
    expect((donut.series as Array<{ data: unknown[] }>)[0]?.data).toHaveLength(4)
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
  it('按项目名称查询必须先选完整且不超过 366 天的日期范围', () => {
    expect(validateTenderSearch(initialQuery())).toBeNull()
    const emptyDates = { ...initialQuery(), public_date_from: '', public_date_to: '' }
    expect(validateTenderSearch({ ...emptyDates, project_name: '智慧城市' })).toContain('日期范围')
    expect(validateTenderSearch({ ...emptyDates, project_name: '智慧城市', collect_date_from: '2026-11-01' })).toContain('日期范围')
    expect(validateTenderSearch({
      ...emptyDates,
      project_name: '智慧城市',
      collect_date_from: '2025-01-01',
      collect_date_to: '2026-11-12',
    })).toContain('366')
    expect(validateTenderSearch({
      ...emptyDates,
      project_name: '智慧城市',
      collect_date_from: '2026-11-01',
      collect_date_to: '2026-11-12',
    })).toBeNull()
    expect(validateTenderSearch({
      ...emptyDates,
      project_name: '智慧城市',
      public_date_from: '2026-11-01',
      public_date_to: '2026-11-12',
    })).toBeNull()
  })
  it('分省统计按全量及通过量排序并计算通过率与拆解量', () => {
    const sample = [
      { province: '广东省', purchaser: 60, winbid: 40, tagged: 20, enriched: 20, scenario: 0, purchaser_passed: 12, winbid_passed: 8 },
      { province: '浙江省', purchaser: 30, winbid: 20, tagged: 40, enriched: 40, scenario: 0, purchaser_passed: 25, winbid_passed: 15 },
      { province: '', purchaser: 10, winbid: 0, tagged: 0, enriched: 0, scenario: 0, purchaser_passed: 0, winbid_passed: 0 },
    ]
    const totalRows = buildProvinceRows(sample, [], 'total')
    const topTotal = totalRows[0]!
    const lastTotal = totalRows[2]!
    expect(topTotal.name).toBe('广东省')
    expect(topTotal.passRate).toBe('20.0%')
    expect(topTotal.unpassed).toBe(80)
    expect(topTotal.passPurchaser).toBe(12)
    expect(topTotal.passWinbid).toBe(8)
    expect(lastTotal.name).toBe('未填写省份')

    const deliveryRows = buildProvinceRows(sample, [], 'delivery')
    const topDelivery = deliveryRows[0]!
    expect(topDelivery.name).toBe('浙江省')
    expect(topDelivery.passed).toBe(40)
    expect(topDelivery.passPurchaser).toBe(25)
    expect(topDelivery.passWinbid).toBe(15)
    expect(topDelivery.passRate).toBe('80.0%')
  })
  it('分省统计支持码表省份名称过滤', () => {
    const sample = [
      { province: '广东省', purchaser: 60, winbid: 40, tagged: 20, enriched: 20, scenario: 0 },
      { province: '浙江省', purchaser: 30, winbid: 20, tagged: 40, enriched: 40, scenario: 0 },
    ]
    const filtered = buildProvinceRows(sample, ['浙江'], 'delivery')
    expect(filtered).toHaveLength(1)
    expect(filtered[0]?.name).toBe('浙江省')
  })
  it('详情页按业务主题分组且列表字段核心信息前置', () => {
    const purchaserCols = tenderColumns('purchaser').map(col => col.prop)
    expect(purchaserCols.slice(0, 3)).toEqual(['project_name', 'project_status', 'public_date'])
    const sections = buildDetailSections(tenderColumns('winbid'), tenderDetailGroups('winbid'))
    expect(sections.map(s => s.title)).toEqual(['项目核心信息', '招中标主体与地区', '行业与场景标签', SYSTEM_SECTION])
  })
  it('方案A默认注入近7天发布时间，支持清空兜底且不覆盖已有日期', () => {
    const testDate = new Date(2026, 10, 13) // 2026-11-13
    expect(recentDaysRange(7, testDate)).toEqual(['2026-11-07', '2026-11-13'])

    // initialQuery 默认带入近 7 天发布时间
    const defaultQuery = initialQuery()
    expect(defaultQuery.public_date_from).toBeTruthy()
    expect(defaultQuery.public_date_to).toBeTruthy()

    // 若日期被清空：applyDefaultDateRange 自动补齐近 7 天
    const emptyDateQuery = { ...initialQuery(), public_date_from: '', public_date_to: '' }
    expect(applyDefaultDateRange(emptyDateQuery)).toBe(true)
    expect(emptyDateQuery.public_date_from).toBeTruthy()
    expect(emptyDateQuery.public_date_to).toBeTruthy()

    // 已有其他日期时：不覆盖
    const queryWithOtherDate = { ...initialQuery(), public_date_from: '', public_date_to: '', collect_date_from: '2026-11-01' }
    expect(applyDefaultDateRange(queryWithOtherDate)).toBe(false)
    expect(queryWithOtherDate.public_date_from).toBe('')
  })
})
