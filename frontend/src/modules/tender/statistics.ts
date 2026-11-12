import type { TenderPoint } from '@/api/tender'
import type { ChartOption, ChartPalette } from '@/components/charts/echarts'
export function recentRange(now = new Date()): [string, string] {
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
  const end = new Date(`${day}T00:00:00+08:00`)
  const start = new Date(end.getTime() - 6 * 86_400_000)
  const format = (date: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
  return [format(start), day]
}
export function statisticsChart(points: TenderPoint[], palette: ChartPalette, mode: 'intake' | 'work'): ChartOption {
  const series = mode === 'intake'
    ? [{ key: 'purchaser', name: '招标', color: palette.primary }, { key: 'winbid', name: '中标', color: palette.success }]
    : [{ key: 'tagged', name: '信息化标签', color: palette.primary }, { key: 'enriched', name: '基础字段补充', color: palette.warning }, { key: 'scenario', name: '场景补充', color: palette.muted }]
  return {
    tooltip: { trigger: 'axis', renderMode: 'richText' },
    legend: { top: 0, bottom: 'auto', textStyle: { color: palette.ink } },
    grid: { top: 45, left: 65, right: 24, bottom: 35 },
    xAxis: { type: 'category', data: points.map(point => point.date), axisLabel: { color: palette.inkMuted } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: palette.inkMuted }, splitLine: { lineStyle: { color: palette.gridLine } } },
    series: series.map(item => ({ name: item.name, type: 'bar', itemStyle: { color: item.color }, data: points.map(point => point[item.key as keyof TenderPoint]) })),
  }
}
