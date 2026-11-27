import type { LibraryBreakdown, ThinktankStatsLibrary, TrendPoint } from '@/api/thinktankStats'
import { tooltipStyle, type ChartOption, type ChartPalette } from '@/components/charts/echarts'

export const LIBRARY_COLOR_KEY: Record<'knowledge' | 'reports' | 'proposals', keyof ChartPalette> = {
  knowledge: 'primary',
  reports: 'success',
  proposals: 'warning',
}

export function buildLibraryDonutOption(
  libraries: LibraryBreakdown[],
  selected: ThinktankStatsLibrary,
  palette: ChartPalette,
): ChartOption {
  const total = libraries.reduce((sum, item) => sum + item.files, 0)
  const data = libraries.map(lib => {
    const color = palette[LIBRARY_COLOR_KEY[lib.key]]
    const dimmed = selected !== 'all' && selected !== lib.key
    return {
      name: lib.label,
      value: lib.files,
      libraryKey: lib.key,
      itemStyle: {
        color,
        opacity: dimmed ? 0.25 : 1,
        borderColor: palette.surface,
        borderWidth: total > 0 ? 2 : 0,
      },
    }
  })

  return {
    tooltip: {
      ...tooltipStyle(palette),
      trigger: 'item',
      formatter: (params: { name: string; value: number; percent: number }) =>
        `<strong>${params.name}</strong><br/>文件数：${params.value.toLocaleString('zh-CN')} 份（${params.percent}%）`,
    },
    series: [
      {
        name: '三库资产构成',
        type: 'pie',
        radius: ['60%', '84%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: false,
        label: { show: false },
        emphasis: { scale: true, scaleSize: 4 },
        data: total > 0 ? data : [{ name: '暂无资产', value: 1, itemStyle: { color: palette.gridLine } }],
      },
    ],
  }
}

function axisCommon(palette: ChartPalette) {
  return {
    axisLine: { lineStyle: { color: palette.border } },
    axisTick: { show: false },
    axisLabel: { color: palette.inkMuted, fontSize: 11.5 },
    splitLine: { lineStyle: { color: palette.gridLine, type: 'dashed' } },
  }
}

export function buildProduceTrendOption(
  points: TrendPoint[],
  style: 'bar' | 'line',
  palette: ChartPalette,
): ChartOption {
  const labels = points.map(p => p.label)
  const isBar = style === 'bar'
  const baseSeries = isBar
    ? [
        {
          name: '资料库上传',
          type: 'bar',
          stack: 'uploads',
          barMaxWidth: 28,
          itemStyle: { color: palette.primary, borderRadius: [0, 0, 0, 0] },
          data: points.map(p => p.knowledge_uploads),
        },
        {
          name: '报告库上传',
          type: 'bar',
          stack: 'uploads',
          barMaxWidth: 28,
          itemStyle: { color: palette.success },
          data: points.map(p => p.reports_uploads),
        },
        {
          name: '方案库上传',
          type: 'bar',
          stack: 'uploads',
          barMaxWidth: 28,
          itemStyle: { color: palette.warning, borderRadius: [4, 4, 0, 0] },
          data: points.map(p => p.proposals_uploads),
        },
      ]
    : [
        {
          name: '新增上传合计',
          type: 'line',
          smooth: 0.35,
          symbolSize: 6,
          lineStyle: { width: 2.5, color: palette.primary },
          itemStyle: { color: palette.primary },
          areaStyle: {
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
          },
          data: points.map(p => p.total_uploads),
        },
      ]

  return {
    tooltip: { ...tooltipStyle(palette), trigger: 'axis', axisPointer: { type: isBar ? 'shadow' : 'line' } },
    grid: { top: 18, right: 20, bottom: 28, left: 46 },
    xAxis: { type: 'category', data: labels, ...axisCommon(palette), splitLine: { show: false } },
    yAxis: { type: 'value', minInterval: 1, ...axisCommon(palette) },
    series: [
      ...baseSeries,
      {
        name: '标签治理 / 编辑',
        type: 'line',
        smooth: 0.35,
        symbolSize: 6,
        lineStyle: { width: 2, type: 'dashed', color: palette.muted },
        itemStyle: { color: palette.muted },
        data: points.map(p => p.governance),
      },
    ],
  }
}

export function buildConsumeTrendOption(
  points: TrendPoint[],
  style: 'bar' | 'line',
  palette: ChartPalette,
): ChartOption {
  const labels = points.map(p => p.label)
  const isBar = style === 'bar'
  return {
    tooltip: { ...tooltipStyle(palette), trigger: 'axis', axisPointer: { type: 'line' } },
    grid: { top: 18, right: 48, bottom: 28, left: 48 },
    xAxis: { type: 'category', data: labels, ...axisCommon(palette), splitLine: { show: false } },
    yAxis: [
      { type: 'value', minInterval: 1, ...axisCommon(palette) },
      {
        type: 'value',
        minInterval: 1,
        ...axisCommon(palette),
        splitLine: { show: false },
        axisLabel: { color: palette.inkMuted, fontSize: 11.5, formatter: '{value}人' },
      },
    ],
    series: [
      {
        name: '在线预览',
        type: 'line',
        smooth: 0.35,
        symbolSize: 6,
        lineStyle: { width: 2.5, color: palette.primary },
        itemStyle: { color: palette.primary },
        areaStyle: {
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
        },
        data: points.map(p => p.previews),
      },
      {
        name: '原文件下载',
        type: isBar ? 'bar' : 'line',
        barMaxWidth: 22,
        smooth: 0.35,
        itemStyle: { color: palette.success, borderRadius: isBar ? [4, 4, 0, 0] : 0 },
        lineStyle: { width: 2.2, color: palette.success },
        data: points.map(p => p.downloads),
      },
      {
        name: '去重活跃人数',
        type: 'line',
        yAxisIndex: 1,
        smooth: 0.35,
        symbolSize: 6,
        lineStyle: { width: 2, type: 'dashed', color: palette.warning },
        itemStyle: { color: palette.warning },
        data: points.map(p => p.active_users),
      },
    ],
  }
}

export function formatDelta(delta: number | null): { text: string; tone: 'up' | 'down' | 'flat' } {
  if (delta === null) return { text: '全量周期', tone: 'flat' }
  if (delta > 0) return { text: `↑ ${delta.toFixed(1)}%`, tone: 'up' }
  if (delta < 0) return { text: `↓ ${Math.abs(delta).toFixed(1)}%`, tone: 'down' }
  return { text: '持平 0.0%', tone: 'flat' }
}

export function avatarToneIndex(seed: string): number {
  let hash = 0
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0
  return (hash % 8) + 1
}
