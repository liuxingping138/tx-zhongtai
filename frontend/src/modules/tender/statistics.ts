import type { TenderPoint } from '@/api/tender'
import { tooltipStyle, type ChartOption, type ChartPalette } from '@/components/charts/echarts'

export function recentRange(now = new Date(), days = 7): [string, string] {
  const format = (date: Date) =>
    new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
  const day = format(now)
  const end = new Date(`${day}T00:00:00+08:00`)
  const start = new Date(end.getTime() - (days - 1) * 86_400_000)
  return [format(start), day]
}

export function compactCount(value: number): string {
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(2)}亿`
  if (value >= 10_000) return `${(value / 10_000).toFixed(1)}万`
  return value.toLocaleString('zh-CN')
}

export function shortProvinceName(name: string): string {
  return name.replace(/(?:维吾尔|壮族|回族)?自治区$|特别行政区$|[省市]$/, '')
}

function compactTick(value: number): string {
  if (value >= 10_000) {
    const wan = value / 10_000
    return Number.isInteger(wan) ? `${wan}万` : `${wan.toFixed(1)}万`
  }
  return value.toLocaleString('zh-CN')
}

export function statisticsChart(
  points: TenderPoint[],
  palette: ChartPalette,
  mode: 'intake' | 'work',
  chartType: 'bar' | 'line' = 'bar',
): ChartOption {
  const seriesSpecs = mode === 'intake'
    ? [
        { key: 'purchaser', name: '招标', color: palette.primary },
        { key: 'winbid', name: '中标', color: palette.success },
      ]
    : [
        { key: 'tagged', name: '信息化标签', color: palette.primary },
        { key: 'enriched', name: '基础字段补充', color: palette.warning },
        { key: 'scenario', name: '场景补充', color: palette.muted },
      ]

  const dates = points.map(point => point.date?.slice(5) ?? '')
  const avg = mode === 'intake' && points.length
    ? Math.round(points.reduce((sum, item) => sum + item.purchaser + item.winbid, 0) / points.length)
    : 0

  return {
    tooltip: { trigger: 'axis', ...tooltipStyle(palette) },
    legend: {
      top: 0,
      left: 0,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: palette.inkMuted, fontSize: 12 },
    },
    grid: { top: 38, left: 54, right: 16, bottom: 26 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: palette.inkMuted, fontSize: 12 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: palette.inkMuted, fontSize: 12, formatter: compactTick },
      splitLine: { lineStyle: { color: palette.gridLine, type: 'dashed' } },
    },
    series: seriesSpecs.map((item, index) => {
      const data = points.map(point => Number(point[item.key as keyof TenderPoint] ?? 0))
      if (chartType === 'line' && mode === 'intake') {
        return {
          name: item.name,
          type: 'line',
          smooth: 0.32,
          symbolSize: 6,
          lineStyle: { width: 2.5, color: item.color },
          itemStyle: { color: item.color },
          areaStyle: index === 0
            ? {
                color: {
                  type: 'linear',
                  x: 0,
                  y: 0,
                  x2: 0,
                  y2: 1,
                  colorStops: [
                    { offset: 0, color: palette.areaTop },
                    { offset: 1, color: palette.areaBottom },
                  ],
                },
              }
            : undefined,
          data,
        }
      }
      return {
        name: item.name,
        type: 'bar',
        barMaxWidth: 24,
        itemStyle: { color: item.color, borderRadius: [5, 5, 0, 0] },
        data,
        markLine: mode === 'intake' && index === 0 && avg > 0
          ? {
              silent: true,
              symbol: 'none',
              lineStyle: { color: palette.primaryLight, type: 'dashed', width: 1.5 },
              label: { formatter: `日均 ${compactTick(avg)}`, position: 'insideEndTop', color: palette.primary, fontSize: 12 },
              data: [{ yAxis: avg }],
            }
          : undefined,
      }
    }),
  }
}

export function structureDonutOption(purchaser: number, winbid: number, palette: ChartPalette): ChartOption {
  return {
    tooltip: {
      trigger: 'item',
      ...tooltipStyle(palette),
      formatter: '{b}：{c}（{d}%）',
    },
    series: [
      {
        type: 'pie',
        radius: ['62%', '84%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: false,
        padAngle: 3,
        itemStyle: { borderRadius: 6, borderColor: palette.surface, borderWidth: 2 },
        label: { show: false },
        data: [
          { name: '招标原始库', value: purchaser, itemStyle: { color: palette.primary } },
          { name: '中标原始库', value: winbid, itemStyle: { color: palette.success } },
        ],
      },
    ],
  }
}
