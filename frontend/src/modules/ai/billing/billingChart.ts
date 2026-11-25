/** 每日费用堆叠柱：按天动态顶段圆角、自适应柱宽、日均虚线基准与结构化财务悬浮卡。 */
import { tooltipStyle, type ChartOption, type ChartPalette } from '@/components/charts/echarts'
import { money } from './billing'

interface Series {
  name: string
  color: string
  data: number[]
}

interface TooltipParam {
  dataIndex: number
  seriesName: string
  value: number | { value: number }
  color?: string
  marker?: string
}

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function dayWithWeekday(isoDate: string): string {
  const ts = Date.parse(`${isoDate}T00:00:00Z`)
  if (Number.isNaN(ts)) return isoDate
  return `${isoDate} ${WEEKDAYS[new Date(ts).getUTCDay()] ?? ''}`
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function formatTooltip(
  rawParams: TooltipParam | TooltipParam[],
  days: string[],
  dailyAvg: number,
  palette: ChartPalette,
): string {
  const params = Array.isArray(rawParams) ? rawParams : [rawParams]
  const day = days[params[0]?.dataIndex ?? -1] ?? ''
  const parts = params
    .map(item => ({
      name: item.seriesName,
      color: item.color ?? palette.primary,
      val: typeof item.value === 'object' && item.value !== null ? Number(item.value.value) : Number(item.value ?? 0),
    }))
    .filter(item => item.val > 0)
    .sort((a, b) => b.val - a.val)

  const total = parts.reduce((sum, item) => sum + item.val, 0)
  const deltaPct = dailyAvg > 0 ? ((total - dailyAvg) / dailyAvg) * 100 : 0
  const deltaHtml = total > 0 && dailyAvg > 0
    ? `<span style="color:${palette.inkMuted};font-size:11px;margin-left:8px;">较日均 ${deltaPct >= 0 ? '+' : ''}${deltaPct.toFixed(0)}%</span>`
    : ''
  const header = `<div style="display:flex;align-items:baseline;justify-content:space-between;gap:16px;padding-bottom:6px;margin-bottom:6px;border-bottom:1px solid ${palette.border};">`
    + `<span style="font-weight:600;color:${palette.ink};">${escapeHtml(dayWithWeekday(day))}</span>`
    + `<span style="font-weight:650;color:${palette.primary};">${money(total)}${deltaHtml}</span></div>`

  if (!parts.length) {
    return `${header}<div style="color:${palette.inkMuted};font-size:12px;">这天没有花费</div>`
  }

  const rowsHtml = parts.map(item => {
    const pct = total > 0 ? ((item.val / total) * 100).toFixed(1) : '0.0'
    return `<div style="display:flex;align-items:center;justify-content:space-between;gap:18px;line-height:1.85;">`
      + `<span style="display:inline-flex;align-items:center;gap:6px;min-width:0;color:${palette.ink};">`
      + `<i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${item.color};flex:none;"></i>`
      + `<span style="display:block;max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(item.name)}</span></span>`
      + `<span style="display:inline-flex;align-items:center;gap:8px;flex:none;white-space:nowrap;font-variant-numeric:tabular-nums;">`
      + `<span style="color:${palette.inkMuted};font-size:11px;">${pct}%</span>`
      + `<span style="font-weight:500;color:${palette.ink};min-width:62px;text-align:right;">${money(item.val)}</span></span></div>`
  }).join('')
  return `${header}${rowsHtml}`
}

function avgMarkLine(dailyAvg: number, palette: ChartPalette) {
  return {
    symbol: ['none', 'none'],
    silent: true,
    lineStyle: { color: palette.inkMuted, type: [4, 4], width: 1, opacity: 0.65 },
    label: {
      show: true,
      position: 'end',
      distance: 8,
      formatter: () => `日均 ${money(dailyAvg)}`,
      color: palette.inkMuted,
      fontSize: 11,
      fontWeight: 500,
    },
    data: [{ yAxis: dailyAvg }],
  }
}

export function costOption(days: string[], series: Series[], palette: ChartPalette): ChartOption {
  const grandTotal = days.reduce((sum, _, idx) => sum + series.reduce((s, item) => s + (item.data[idx] ?? 0), 0), 0)
  const dailyAvg = days.length > 0 ? grandTotal / days.length : 0
  const showAvg = dailyAvg > 0 && days.length > 1
  const rightPad = showAvg ? Math.max(92, (`日均 ${money(dailyAvg)}`).length * 8 + 18) : 12
  // 找出每一天堆叠在最上面的非零系列下标，保证每根柱子顶部都有细腻圆角。
  const topByDay = days.map((_, dayIdx) => {
    for (let sIdx = series.length - 1; sIdx >= 0; sIdx--) {
      if ((series[sIdx]?.data[dayIdx] ?? 0) > 0) return sIdx
    }
    return -1
  })
  const barMaxWidth = days.length > 45 ? 12 : days.length > 20 ? 20 : 28

  return {
    animationDuration: 260,
    animationEasing: 'cubicOut',
    legend: {
      type: 'scroll',
      left: 0,
      top: 0,
      right: 0,
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 18,
      icon: 'roundRect',
      pageIconColor: palette.inkMuted,
      pageTextStyle: { color: palette.inkMuted },
      textStyle: { color: palette.inkMuted, fontSize: 12, padding: [0, 0, 0, 2] },
    },
    grid: { left: 6, right: rightPad, top: 48, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      confine: true,
      transitionDuration: 0.12,
      axisPointer: { type: 'shadow', shadowStyle: { color: palette.weekendBand } },
      ...tooltipStyle(palette),
      extraCssText: `border-radius: 10px; box-shadow: ${palette.tooltipShadow}; font-variant-numeric: tabular-nums;`,
      formatter: (params: TooltipParam | TooltipParam[]) => formatTooltip(params, days, dailyAvg, palette),
    },
    xAxis: {
      type: 'category',
      data: days.map(day => day.slice(5)),
      axisLine: { lineStyle: { color: palette.border } },
      axisTick: { show: false },
      axisLabel: { color: palette.inkMuted, fontSize: 11.5, margin: 10, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: palette.inkMuted, fontSize: 11.5, formatter: (val: number) => (val === 0 ? '0' : `¥${val}`) },
      splitLine: { lineStyle: { color: palette.border, type: 'dashed' } },
    },
    series: series.map((item, sIdx) => ({
      name: item.name,
      type: 'bar',
      stack: 'cost',
      color: item.color,
      barMaxWidth,
      emphasis: { focus: 'series', blurScope: 'coordinateSystem' },
      itemStyle: { borderColor: palette.surface, borderWidth: days.length > 60 ? 0.5 : 1 },
      data: item.data.map((value, dayIdx) => ({
        value,
        itemStyle: { borderRadius: topByDay[dayIdx] === sIdx ? [3.5, 3.5, 0, 0] : 0 },
      })),
      ...(sIdx === 0 && showAvg ? { markLine: avgMarkLine(dailyAvg, palette) } : {}),
    })),
  }
}
