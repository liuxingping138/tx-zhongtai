import { computed, type ComputedRef } from 'vue'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

import { useTheme } from '@/composables/useTheme'

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
  /** 卡片底色：环形图扇区、堆叠柱之间留的缝用它，和卡片融在一起。 */
  surface: string
  success: string
  warning: string
  danger: string
  muted: string
}

const PALETTE_VARS: Record<keyof ChartPalette, [string, string]> = {
  primary: ['--zt-blue-600', '#3558de'],
  primaryLight: ['--el-color-primary-light-5', '#9aacee'],
  ink: ['--zt-ink-900', '#162638'],
  inkMuted: ['--zt-ink-500', '#5f6c7b'],
  border: ['--zt-border', '#dfe5eb'],
  surface: ['--zt-panel', '#ffffff'],
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

/** 响应式图表调色盘：切换深浅色主题时自动重算 ECharts 颜色与网格线 */
export function useChartPalette(style?: Pick<CSSStyleDeclaration, 'getPropertyValue'>): ComputedRef<ChartPalette> {
  const { isDark } = useTheme()
  return computed(() => (void isDark.value, chartPalette(style ?? globalThis.getComputedStyle?.(globalThis.document?.documentElement))))
}

/** Google Material 3 风格悬浮提示框样式 */
export function tooltipStyle(palette: ChartPalette) {
  return {
    backgroundColor: palette.surface,
    borderColor: palette.border,
    borderWidth: 1,
    padding: [10, 14],
    textStyle: { color: palette.ink, fontSize: 12.5, lineHeight: 20 },
    extraCssText: 'border-radius: 10px; box-shadow: 0 12px 32px rgba(15, 23, 42, 0.14), 0 2px 6px rgba(15, 23, 42, 0.06);',
  }
}
