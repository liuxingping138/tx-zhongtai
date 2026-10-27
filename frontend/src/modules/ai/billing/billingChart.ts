/** 每日费用堆叠柱：一天一根，按模型（或用途）分段，悬停看每段金额和当天合计。 */
import type { ChartOption, ChartPalette } from '@/components/charts/echarts'
import { money } from './billing'

interface Series {
  name: string
  color: string
  data: number[]
}

export function costOption(days: string[], series: Series[], palette: ChartPalette): ChartOption {
  return {
    legend: { left: 0, top: 0, itemWidth: 12, itemHeight: 12, textStyle: { color: palette.inkMuted } },
    grid: { left: 8, right: 8, top: 44, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number; seriesName: string; value: number; marker: string }[]) => {
        const day = days[params[0]?.dataIndex ?? -1] ?? ''
        const parts = params.filter(item => item.value > 0)
        const total = parts.reduce((sum, item) => sum + item.value, 0)
        const lines = parts.map(item => `${item.marker}${item.seriesName}　${money(item.value)}`)
        return [`<b>${day}</b>　合计 ${money(total)}`, ...(lines.length ? lines : ['这天没有花费'])].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: days.map(day => day.slice(5)),
      axisLine: { lineStyle: { color: palette.border } },
      axisTick: { show: false },
      axisLabel: { color: palette.inkMuted },
    },
    yAxis: {
      type: 'value',
      name: '元',
      nameTextStyle: { color: palette.inkMuted },
      axisLabel: { color: palette.inkMuted },
      splitLine: { lineStyle: { color: palette.border, type: 'dashed' } },
    },
    series: series.map((item, index) => ({
      name: item.name,
      type: 'bar',
      stack: 'cost',
      color: item.color,
      barMaxWidth: 28,
      // 段与段之间留一道白缝，颜色相近的两段也分得开；最上面一段圆角。
      itemStyle: {
        borderColor: palette.surface,
        borderWidth: 1,
        borderRadius: index === series.length - 1 ? [3, 3, 0, 0] : 0,
      },
      emphasis: { focus: 'series' },
      data: item.data,
    })),
  }
}
