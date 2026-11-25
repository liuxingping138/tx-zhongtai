import { describe, expect, it } from 'vitest'

import { chartPalette } from '@/components/charts/echarts'
import { costOption } from './billingChart'

const palette = chartPalette()
const SERIES = [
  { name: '方舟Flash', color: '#2a78d6', data: [1.5, 0.4] },
  { name: '千帆V3.2', color: '#eb6834', data: [0.25, 0] },
]

type Tooltip = {
  formatter: (params: { dataIndex: number; seriesName: string; value: number | { value: number }; color?: string }[]) => string
}

interface BarDatum {
  value: number
  itemStyle: { borderRadius: unknown }
}

describe('每日费用堆叠柱', () => {
  it('按天动态给最顶部非零段加圆角，并把日均标签挂在右侧留白避免与柱子相撞', () => {
    const option = costOption(['2026-10-21', '2026-10-22'], SERIES, palette) as {
      grid: { right: number }
      series: { name: string; stack: string; color: string; data: BarDatum[]; markLine?: { label: { position: string }; data: { yAxis: number }[] } }[]
      xAxis: { data: string[] }
    }
    expect(option.xAxis.data).toEqual(['10-21', '10-22'])
    expect(option.series.map(item => [item.name, item.stack, item.color])).toEqual([
      ['方舟Flash', 'cost', '#2a78d6'],
      ['千帆V3.2', 'cost', '#eb6834'],
    ])
    // 第 1 天两个系列都有值，仅顶部系列（千帆V3.2）圆角；第 2 天千帆为 0，顶段自动落到方舟Flash
    expect(option.series[0]?.data.map(d => d.itemStyle.borderRadius)).toEqual([0, [3.5, 3.5, 0, 0]])
    expect(option.series[1]?.data.map(d => d.itemStyle.borderRadius)).toEqual([[3.5, 3.5, 0, 0], 0])
    expect(option.series[0]?.markLine?.data[0]?.yAxis).toBeCloseTo(1.075)
    expect(option.series[0]?.markLine?.label.position).toBe('end')
    expect(option.grid.right).toBeGreaterThanOrEqual(92)
  })

  it('悬停写带星期的日期、当天合计、较日均偏离及独立省略号分项；整天没花钱写明', () => {
    const { tooltip } = costOption(['2026-10-21', '2026-10-22'], SERIES, palette) as { tooltip: Tooltip }
    const day = tooltip.formatter([
      { dataIndex: 0, seriesName: '方舟Flash', value: { value: 1.5 }, color: '#2a78d6' },
      { dataIndex: 0, seriesName: '千帆V3.2', value: { value: 0.25 }, color: '#eb6834' },
    ])
    expect(day).toContain('2026-10-21 周三')
    expect(day).toContain('¥1.75')
    expect(day).toContain('较日均 +63%')
    expect(day).toContain('display:block;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">方舟Flash</span>')
    expect(day).toContain('85.7%')
    expect(tooltip.formatter([{ dataIndex: 1, seriesName: '方舟Flash', value: 0 }])).toContain('这天没有花费')
  })
})
