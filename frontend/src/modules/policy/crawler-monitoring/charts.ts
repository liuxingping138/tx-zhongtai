import type {
  CrawlerOverviewData,
  CrawlerHealth,
  CrawlerTrendDays,
  CrawlerTrendPoint,
  SiteStatus,
} from '@/api/crawlerMonitoring'
import { tooltipStyle, type ChartOption, type ChartPalette } from '@/components/charts/echarts'
import { compactCount } from './filters'
import { percent } from './provinceView'

export {
  percent,
  provinceRanks,
  provinceSelected,
  provinceShortName,
  provinceTile,
  sortProvinces,
  type ProvinceRankRow,
  type ProvinceTile,
} from './provinceView'

function parseDay(value: string): Date {
  const [year = 0, month = 1, day = 1] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function formatDay(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function isWeekend(value: string): boolean {
  const day = parseDay(value).getDay()
  return day === 0 || day === 6
}

export type TrendUnit = 'day' | 'week' | 'month'

export const TREND_RANGES: { value: CrawlerTrendDays; label: string; unit: TrendUnit }[] = [
  { value: 7, label: '7 天', unit: 'day' },
  { value: 30, label: '1 个月', unit: 'day' },
  { value: 90, label: '1 个季度', unit: 'week' },
  { value: 365, label: '1 年', unit: 'month' },
]

function trendUnit(days: CrawlerTrendDays): TrendUnit {
  return TREND_RANGES.find(item => item.value === days)?.unit ?? 'day'
}

export interface TrendBucket {
  /** 当天、周一或当月 1 日 */
  start: string
  label: string
  rows: number
  days: number
  /** 日均条数：首尾不满一周、一个月的段按天平均，才不会看着像骤降。 */
  average: number
}

/** 7 天、1 个月按天，1 个季度按周（周一为起点），1 年按月。 */
export function trendBuckets(points: CrawlerTrendPoint[], days: CrawlerTrendDays): TrendBucket[] {
  const unit = trendUnit(days)
  const buckets = new Map<string, { rows: number; days: number }>()
  for (const point of points) {
    const date = parseDay(point.date)
    if (unit === 'month') date.setDate(1)
    if (unit === 'week') date.setDate(date.getDate() - ((date.getDay() + 6) % 7))
    const key = formatDay(date)
    const bucket = buckets.get(key) ?? { rows: 0, days: 0 }
    buckets.set(key, { rows: bucket.rows + point.rows, days: bucket.days + 1 })
  }
  return [...buckets].map(([start, bucket]) => ({
    start,
    label: unit === 'month' ? `${Number(start.slice(5, 7))}月` : `${Number(start.slice(5, 7))}/${Number(start.slice(8))}`,
    rows: bucket.rows,
    days: bucket.days,
    average: Math.round(bucket.rows / bucket.days),
  }))
}

/** 「3.0 万条」「700 条」：带万、亿时单位紧跟，不留空格。 */
export function countText(value: number, unit = '条'): string {
  const compact = compactCount(value)
  return /[万亿]$/.test(compact) ? `${compact}${unit}` : `${compact} ${unit}`
}

function sumRows(points: CrawlerTrendPoint[]): number {
  return points.reduce((sum, point) => sum + point.rows, 0)
}

/** 领导关心「平时多少、最近怎样」，不报峰值：峰值多半是某天集中补采，没有代表性。 */
export function trendSummary(points: CrawlerTrendPoint[], days: CrawlerTrendDays): string {
  if (!points.length) return '所选时间范围内没有采集数据'
  const range = `近 ${TREND_RANGES.find(item => item.value === days)?.label ?? `${days} 天`}`
  const average = Math.round(sumRows(points) / points.length)
  return `${range}共采集 ${countText(sumRows(points))}，日均 ${average.toLocaleString()} 条`
}

/** Y 轴大数按万缩写，与顶部卡片统一并节省左侧宽度。 */
function compactTick(value: number): string {
  if (value >= 10000) {
    const wan = value / 10000
    return Number.isInteger(wan) ? `${wan}万` : `${wan.toFixed(1)}万`
  }
  return value.toLocaleString()
}

function axisStyle(palette: ChartPalette) {
  return {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: palette.inkMuted },
  }
}

function valueAxis(name: string, palette: ChartPalette, showGrid: boolean) {
  return {
    type: 'value',
    name,
    nameTextStyle: { color: palette.inkMuted },
    axisLabel: { color: palette.inkMuted, formatter: compactTick },
    splitLine: { show: showGrid, lineStyle: { color: palette.gridLine, type: 'dashed' } },
  }
}

function areaGradient(palette: ChartPalette) {
  return {
    type: 'linear',
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: palette.areaTop },
      { offset: 1, color: palette.areaBottom },
    ],
  }
}

function weekendBands(dates: string[]): [{ xAxis: number; yAxis: 'min' }, { xAxis: number; yAxis: 'max' }][] {
  const bands: [{ xAxis: number; yAxis: 'min' }, { xAxis: number; yAxis: 'max' }][] = []
  let start = -1
  dates.forEach((date, index) => {
    if (isWeekend(date)) {
      if (start < 0) start = index
      return
    }
    if (start >= 0 && index - 1 > start) bands.push([{ xAxis: start, yAxis: 'min' }, { xAxis: index - 1, yAxis: 'max' }])
    start = -1
  })
  if (start >= 0 && dates.length - 1 > start) {
    bands.push([{ xAxis: start, yAxis: 'min' }, { xAxis: dates.length - 1, yAxis: 'max' }])
  }
  return bands
}

function averageMarkLine(value: number, label: string, palette: ChartPalette) {
  return {
    silent: true,
    symbol: ['none', 'none'],
    lineStyle: { color: palette.inkMuted, type: 'dashed', width: 1.2 },
    label: { show: true, position: 'insideEndTop', color: palette.inkMuted, formatter: `${label} ${compactTick(value)}` },
    data: [{ yAxis: value }],
  }
}

function trendTooltipText(bucket: TrendBucket, unit: TrendUnit, overallAvg: number, showDelta: boolean): string {
  if (unit !== 'day') {
    const title = unit === 'month' ? bucket.start.slice(0, 7) : `${bucket.start} 起一周`
    return [`<b>${title}</b>`, `日均 ${bucket.average.toLocaleString()} 条`, `共 ${bucket.rows.toLocaleString()} 条（${bucket.days} 天）`].join('<br/>')
  }
  const tag = isWeekend(bucket.start) ? '（周末）' : ''
  const diff = overallAvg ? Math.round(((bucket.rows - overallAvg) / overallAvg) * 100) : 0
  const vsAvg = showDelta && overallAvg ? `较均值 ${diff >= 0 ? `+${diff}` : diff}%` : ''
  return [`<b>${bucket.start}${tag}</b>`, `采集 ${bucket.rows.toLocaleString()} 条`, vsAvg].filter(Boolean).join('<br/>')
}

function trendSeries(buckets: TrendBucket[], unit: TrendUnit, days: CrawlerTrendDays, avg: number, palette: ChartPalette) {
  const markLine = buckets.length ? averageMarkLine(avg, '均值', palette) : undefined
  if (days === 7) {
    return {
      name: '每日采集量',
      type: 'bar',
      barMaxWidth: 28,
      data: buckets.map(bucket => ({
        value: bucket.average,
        itemStyle: { color: isWeekend(bucket.start) ? palette.weekendBar : palette.primary, borderRadius: [4, 4, 0, 0] },
      })),
      markLine,
    }
  }
  const daily = unit === 'day'
  const bands = daily ? weekendBands(buckets.map(bucket => bucket.start)) : []
  return {
    name: daily ? '每日采集量' : `每${unit === 'month' ? '月' : '周'}日均采集量`,
    type: 'line',
    smooth: 0.22,
    showSymbol: false,
    symbol: 'circle',
    symbolSize: 6,
    lineStyle: { width: 2.2, color: palette.primary },
    itemStyle: { color: palette.primary, borderColor: palette.surface, borderWidth: 2 },
    areaStyle: { color: areaGradient(palette) },
    data: buckets.map(bucket => bucket.average),
    markLine,
    markArea: bands.length ? { silent: true, itemStyle: { color: palette.weekendBand }, data: bands } : undefined,
  }
}

export function trendOption(raw: CrawlerTrendPoint[], days: CrawlerTrendDays, palette: ChartPalette): ChartOption {
  const buckets = trendBuckets(raw, days)
  const unit = trendUnit(days)
  const daily = unit === 'day'
  const isBar = days === 7
  const avg = buckets.length ? Math.round(buckets.reduce((sum, item) => sum + item.average, 0) / buckets.length) : 0

  return {
    grid: { left: 8, right: 12, top: 28, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: isBar
        ? { type: 'shadow', shadowStyle: { color: palette.weekendBand } }
        : { type: 'line', lineStyle: { color: palette.border, type: 'dashed' } },
      ...tooltipStyle(palette),
      formatter: (params: { dataIndex: number }[]) => {
        const bucket = buckets[params[0]?.dataIndex ?? -1]
        return bucket ? trendTooltipText(bucket, unit, avg, !isBar) : ''
      },
    },
    xAxis: { type: 'category', data: buckets.map(bucket => bucket.label), ...axisStyle(palette) },
    yAxis: valueAxis(daily ? '条数' : '日均条数', palette, true),
    series: [trendSeries(buckets, unit, days, avg, palette)],
  }
}

export interface HealthSlice {
  key: keyof Omit<CrawlerHealth, 'long_stale_days'>
  label: string
  hint: string
  value: number
  status: SiteStatus
  color: string
}

export function healthSlices(health: CrawlerHealth, thresholds: { normal_days: number; watch_days: number }, palette: ChartPalette): HealthSlice[] {
  const { normal_days: normalDays, watch_days: watchDays } = thresholds
  return [
    { key: 'normal', label: '正常', hint: `${normalDays} 天内有新数据`, value: health.normal, status: 'normal', color: palette.success },
    { key: 'watch', label: '关注', hint: `${normalDays + 1}–${watchDays} 天无新数据`, value: health.watch, status: 'watch', color: palette.warning },
    { key: 'stale_recent', label: '近期停更', hint: `${watchDays + 1}–${health.long_stale_days} 天无新数据，优先排查`, value: health.stale_recent, status: 'stale', color: palette.danger },
    { key: 'stale_long', label: '长期停更', hint: `超过 ${health.long_stale_days} 天，多半已下线或改版`, value: health.stale_long, status: 'stale', color: palette.muted },
  ]
}

export function healthOption(slices: HealthSlice[], palette: ChartPalette, selected: SiteStatus[] = []): ChartOption {
  return {
    tooltip: { trigger: 'item', ...tooltipStyle(palette), formatter: '{b}：{c} 个（{d}%）' },
    series: [{
      type: 'pie',
      radius: ['64%', '90%'],
      avoidLabelOverlap: false,
      cursor: 'pointer',
      label: { show: false },
      itemStyle: { borderColor: palette.surface, borderWidth: 3, borderRadius: 4 },
      data: slices.map(slice => ({
        name: slice.label,
        value: slice.value,
        itemStyle: {
          color: slice.color,
          opacity: selected.length === 0 || selected.includes(slice.status) ? 1 : 0.22,
        },
      })),
    }],
  }
}

/** 与上一个周期比较的涨跌，上一个周期为 0 时不给百分比。 */
export function changeText(current: number, previous: number): { text: string; trend: 'up' | 'down' | 'flat' } {
  if (!previous) return { text: '前一周期无数据', trend: 'flat' }
  const rate = ((current - previous) / previous) * 100
  if (Math.abs(rate) < 0.05) return { text: '与前一周期持平', trend: 'flat' }
  return { text: `${rate > 0 ? '↑' : '↓'} ${Math.abs(rate).toFixed(1)}%`, trend: rate > 0 ? 'up' : 'down' }
}

export type DeltaTone = 'good' | 'bad' | 'flat'

/** 「较上周 +12」。正常变多是好事，关注和停更变多是坏事，颜色按含义而不是按涨跌。 */
export function weekDelta(current: number, base: number, higherIsBetter: boolean): { text: string; tone: DeltaTone } {
  const diff = current - base
  if (diff === 0) return { text: '与上周持平', tone: 'flat' }
  const good = diff > 0 === higherIsBetter
  return { text: `较上周 ${diff > 0 ? '+' : '−'}${Math.abs(diff).toLocaleString()}`, tone: good ? 'good' : 'bad' }
}

/** 健康率的变化用百分点表达，避免「36% 涨了 2%」这种歧义。 */
export function rateDelta(normal: number, sites: number, baseNormal: number, baseSites: number): { text: string; tone: DeltaTone } {
  if (!sites || !baseSites) return { text: '', tone: 'flat' }
  const points = ((normal / sites) - (baseNormal / baseSites)) * 100
  if (Math.abs(points) < 0.05) return { text: '与上周持平', tone: 'flat' }
  return { text: `较上周 ${points > 0 ? '↑' : '↓'} ${Math.abs(points).toFixed(1)} 个百分点`, tone: points > 0 ? 'good' : 'bad' }
}

export function siteTrendSummary(points: CrawlerTrendPoint[]): string {
  const total = points.reduce((sum, point) => sum + point.rows, 0)
  const activeDays = points.filter(point => point.rows > 0).length
  const last = [...points].reverse().find(point => point.rows > 0)
  if (!last) return `近 ${points.length} 天没有采集到数据`
  return `近 ${points.length} 天共 ${total.toLocaleString()} 条，有数据 ${activeDays} 天，最近一次是 ${last.date}`
}

export function siteTrendOption(points: CrawlerTrendPoint[], palette: ChartPalette): ChartOption {
  const avg = points.length ? Math.round(sumRows(points) / points.length) : 0
  const bands = weekendBands(points.map(point => point.date))
  return {
    grid: { left: 8, right: 12, top: 18, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: palette.border, type: 'dashed' } },
      ...tooltipStyle(palette),
      formatter: (params: { dataIndex: number }[]) => {
        const point = points[params[0]?.dataIndex ?? -1]
        if (!point) return ''
        return `<b>${point.date}${isWeekend(point.date) ? '（周末）' : ''}</b><br/>采集 ${point.rows.toLocaleString()} 条`
      },
    },
    xAxis: { type: 'category', data: points.map(point => point.date.slice(5)), ...axisStyle(palette) },
    yAxis: valueAxis('', palette, true),
    series: [{
      name: '采集量',
      type: 'line',
      smooth: 0.18,
      showSymbol: false,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 1.9, color: palette.primary },
      itemStyle: { color: palette.primary, borderColor: palette.surface, borderWidth: 2 },
      areaStyle: { color: areaGradient(palette) },
      data: points.map(point => point.rows),
      markLine: points.length ? averageMarkLine(avg, '日均', palette) : undefined,
      markArea: bands.length ? { silent: true, itemStyle: { color: palette.weekendBand }, data: bands } : undefined,
    }],
  }
}

export interface HeadlinePart {
  text: string
  strong?: boolean
  tone?: DeltaTone
}

/** 概览顶部的一句话结论：领导不必自己从六张卡片里拼出「整体怎样、变好变坏、该看哪里」。 */
export function headline(overview: CrawlerOverviewData): HeadlinePart[][] {
  const { cards, recent, week_base: base } = overview
  const health: HeadlinePart[] = [
    { text: '共监测 ' },
    { text: cards.sites.toLocaleString(), strong: true },
    { text: ' 个网站，健康率 ' },
    { text: percent(cards.normal, cards.sites), strong: true },
  ]
  const change = base ? rateDelta(cards.normal, cards.sites, base.normal, base.sites) : null
  if (change?.text) health.push({ text: `（${change.text}）`, tone: change.tone })
  const sentences = [health]
  const volume = changeText(recent.rows, recent.previous_rows)
  sentences.push([
    { text: `近 ${recent.days} 天采集 ` },
    { text: countText(recent.rows), strong: true },
    { text: `，较前 ${recent.days} 天 ` },
    { text: volume.text, tone: volume.trend === 'up' ? 'good' : volume.trend === 'down' ? 'bad' : 'flat' },
  ])
  return sentences
}
