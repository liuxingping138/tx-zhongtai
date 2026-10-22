import { describe, expect, it } from 'vitest'

import { chartPalette } from '@/components/charts/echarts'
import { costOption } from './billingChart'

const palette = chartPalette()
const SERIES = [
  { name: '方舟Flash', color: '#2a78d6', data: [1.5, 0] },
  { name: '千帆V3.2', color: '#eb6834', data: [0.25, 0] },
]

type Tooltip = { formatter: (params: { dataIndex: number; seriesName: string; value: number; marker: string }[]) => string }

describe('每日费用堆叠柱', () => {
  it('一个系列一段，堆在同一根柱上，只有最上面一段圆角', () => {
    const option = costOption(['2026-10-21', '2026-10-22'], SERIES, palette) as { series: Record<string, unknown>[]; xAxis: { data: string[] } }
    expect(option.xAxis.data).toEqual(['10-21', '10-22'])
    expect(option.series.map(item => [item.name, item.stack, item.color])).toEqual([['方舟Flash', 'cost', '#2a78d6'], ['千帆V3.2', 'cost', '#eb6834']])
    expect(option.series.map(item => (item.itemStyle as { borderRadius: unknown }).borderRadius)).toEqual([0, [3, 3, 0, 0]])
  })

  it('悬停写当天合计和每段金额，没花钱的段不列；整天没花钱写明', () => {
    const { tooltip } = costOption(['2026-10-21', '2026-10-22'], SERIES, palette) as { tooltip: Tooltip }
    const day = tooltip.formatter([
      { dataIndex: 0, seriesName: '方舟Flash', value: 1.5, marker: '●' },
      { dataIndex: 0, seriesName: '千帆V3.2', value: 0, marker: '●' },
    ])
    expect(day).toBe('<b>2026-10-21</b>　合计 ¥1.50<br/>●方舟Flash　¥1.50')
    expect(tooltip.formatter([{ dataIndex: 1, seriesName: '方舟Flash', value: 0, marker: '●' }])).toContain('这天没有花费')
  })
})
