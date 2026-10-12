import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

// 只注册用到的图表和组件，体积约为整包的三分之一。新图表类型在这里补注册。
echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

export { echarts }
export type ChartOption = echarts.EChartsCoreOption

/** 图表配色取 theme.css 和 Element Plus 的变量，换主题时图表跟着变。 */
export interface ChartPalette {
  primary: string
  primaryLight: string
  ink: string
  inkMuted: string
  border: string
  success: string
  warning: string
  danger: string
  muted: string
}

const PALETTE_VARS: Record<keyof ChartPalette, [string, string]> = {
  primary: ['--zt-blue-600', '#2c68bb'],
  primaryLight: ['--el-color-primary-light-5', '#a0cfff'],
  ink: ['--zt-ink-900', '#20324c'],
  inkMuted: ['--zt-ink-500', '#697386'],
  border: ['--zt-border', '#e3e9f1'],
  success: ['--el-color-success', '#67c23a'],
  warning: ['--el-color-warning', '#e6a23c'],
  danger: ['--el-color-danger', '#f56c6c'],
  muted: ['--el-color-info-light-5', '#c8c9cc'],
}

export function chartPalette(style?: Pick<CSSStyleDeclaration, 'getPropertyValue'>): ChartPalette {
  const read = (name: string, fallback: string) => style?.getPropertyValue(name).trim() || fallback
  return Object.fromEntries(
    Object.entries(PALETTE_VARS).map(([key, [name, fallback]]) => [key, read(name, fallback)]),
  ) as unknown as ChartPalette
}
