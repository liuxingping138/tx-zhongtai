import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

// 只注册用到的图表和组件，体积约为整包的三分之一。新图表类型在这里补注册。
echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

export { echarts }
export type ChartOption = echarts.EChartsCoreOption

/** 柱和环的大面积颜色用克制色板（AntV：面积越大颜色越沉，不用界面上小标签的荧光功能色）。
 * 蓝和中性色仍跟主题变量，换主题时趋势图跟着变。 */
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
  success: ['--chart-normal', '#3d8c6e'],
  warning: ['--chart-watch', '#c4842a'],
  danger: ['--chart-stale', '#d25b4a'],
  muted: ['--chart-long', '#8a7368'],
}

export function chartPalette(style?: Pick<CSSStyleDeclaration, 'getPropertyValue'>): ChartPalette {
  const read = (name: string, fallback: string) => style?.getPropertyValue(name).trim() || fallback
  return Object.fromEntries(
    Object.entries(PALETTE_VARS).map(([key, [name, fallback]]) => [key, read(name, fallback)]),
  ) as unknown as ChartPalette
}
