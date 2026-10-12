import type {
  CrawlerV2Overview,
  CrawlerHealth,
  CrawlerProvince,
  CrawlerTrendDays,
  CrawlerTrendPoint,
  SiteStatus,
} from '@/api/crawlerMonitoringV2'
import type { ChartOption, ChartPalette } from '@/components/charts/echarts'
import { compactCount } from './filters'

const MOVING_WINDOW = 7

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

/** 前 window-1 天凑不满一个窗口，返回 null，图上那一段不画线。 */
export function movingAverage(values: number[], window = MOVING_WINDOW): (number | null)[] {
  return values.map((_, index) => {
    if (index < window - 1) return null
    const slice = values.slice(index - window + 1, index + 1)
    return Math.round(slice.reduce((sum, value) => sum + value, 0) / window)
  })
}

/** 一年按天画太密，按周（周一为起点）汇总：条数求和，网站数取日均。 */
export function weeklyPoints(points: CrawlerTrendPoint[]): CrawlerTrendPoint[] {
  const weeks = new Map<string, { rows: number; sites: number; days: number }>()
  for (const point of points) {
    const date = parseDay(point.date)
    date.setDate(date.getDate() - ((date.getDay() + 6) % 7))
    const key = formatDay(date)
    const week = weeks.get(key) ?? { rows: 0, sites: 0, days: 0 }
    weeks.set(key, { rows: week.rows + point.rows, sites: week.sites + point.sites, days: week.days + 1 })
  }
  return [...weeks].map(([date, week]) => ({ date, rows: week.rows, sites: Math.round(week.sites / week.days) }))
}

/** 「3.0 万条」「700 条」：带万、亿时单位紧跟，不留空格。 */
export function countText(value: number, unit = '条'): string {
  const compact = compactCount(value)
  return /[万亿]$/.test(compact) ? `${compact}${unit}` : `${compact} ${unit}`
}

/** 骤降清单的指标：近 7 天一条都没有时直接说「无数据」，比「↓ 100%」好懂。 */
export function dropText(recentRows: number, dropRate: number): string {
  return recentRows ? `↓ ${Math.round(dropRate * 100)}%` : '近 7 天无数据'
}

function sumRows(points: CrawlerTrendPoint[]): number {
  return points.reduce((sum, point) => sum + point.rows, 0)
}

/** 领导关心「平时多少、最近怎样」，不报峰值：峰值多半是某天集中补采，没有代表性。 */
export function trendSummary(points: CrawlerTrendPoint[], days: CrawlerTrendDays): string {
  if (!points.length) return '所选时间范围内没有采集数据'
  const range = days === 365 ? '近 1 年' : `近 ${days} 天`
  const average = Math.round(sumRows(points) / points.length)
  const recent = points.slice(-7)
  const recentAverage = Math.round(sumRows(recent) / recent.length)
  return `${range}共采集 ${countText(sumRows(points))}，日均 ${average.toLocaleString()} 条；最近 7 天日均 ${recentAverage.toLocaleString()} 条`
}

function axisStyle(palette: ChartPalette) {
  return {
    axisLine: { lineStyle: { color: palette.border } },
    axisTick: { show: false },
    axisLabel: { color: palette.inkMuted },
  }
}

function valueAxis(name: string, palette: ChartPalette, showGrid: boolean) {
  return {
    type: 'value',
    name,
    nameTextStyle: { color: palette.inkMuted },
    axisLabel: { color: palette.inkMuted },
    splitLine: { show: showGrid, lineStyle: { color: palette.border, type: 'dashed' } },
  }
}

function trendTooltip(points: CrawlerTrendPoint[], weekly: boolean) {
  return (params: { dataIndex: number; seriesName: string; value: unknown; marker: string }[]) => {
    const point = points[params[0]?.dataIndex ?? -1]
    if (!point) return ''
    const lines = params
      .filter(item => typeof item.value === 'number')
      .map(item => `${item.marker}${item.seriesName}　${(item.value as number).toLocaleString()} 条`)
    const sites = weekly ? `日均出数网站　${point.sites.toLocaleString()} 个` : `出数网站　${point.sites.toLocaleString()} 个`
    const title = weekly ? `${point.date} 起一周` : `${point.date}${isWeekend(point.date) ? '（周末）' : ''}`
    return [`<b>${title}</b>`, ...lines, sites].join('<br/>')
  }
}

export function trendOption(raw: CrawlerTrendPoint[], days: CrawlerTrendDays, palette: ChartPalette): ChartOption {
  const weekly = days === 365
  const points = weekly ? weeklyPoints(raw) : raw
  // 柱高就是当天条数。不能把高出坐标的日子截成一样高，否则 7 万和 2 万看起来没有差别。
  const bars = points.map(point => ({
    value: point.rows,
    itemStyle: { color: !weekly && isWeekend(point.date) ? palette.primaryLight : palette.primary },
  }))
  // 出数网站数只放进提示框：画成第二条线会随周末大起大落，抢走采集量趋势的注意力。
  const series: Record<string, unknown>[] = [{
    name: weekly ? '每周采集量' : '每日采集量',
    type: 'bar',
    data: bars,
    barMaxWidth: 16,
  }]
  if (!weekly) {
    series.push({
      name: '7 日均值',
      type: 'line',
      data: movingAverage(points.map(point => point.rows)),
      smooth: false,
      showSymbol: false,
      lineStyle: { width: 2, color: palette.ink },
      itemStyle: { color: palette.ink },
    })
  }
  return {
    grid: { left: 8, right: 8, top: 36, bottom: 4, containLabel: true },
    legend: { top: 0, right: 0, itemWidth: 14, itemHeight: 8, textStyle: { color: palette.inkMuted } },
    tooltip: { trigger: 'axis', formatter: trendTooltip(points, weekly) },
    xAxis: { type: 'category', data: points.map(point => (weekly ? `${point.date.slice(5)} 周` : point.date.slice(5))), ...axisStyle(palette) },
    yAxis: valueAxis('条数', palette, true),
    series,
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

export function healthOption(slices: HealthSlice[]): ChartOption {
  return {
    tooltip: { trigger: 'item', formatter: '{b}：{c} 个（{d}%）' },
    series: [{
      type: 'pie',
      radius: ['54%', '90%'],
      avoidLabelOverlap: false,
      label: { show: false },
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      data: slices.map(slice => ({ name: slice.label, value: slice.value, itemStyle: { color: slice.color } })),
    }],
  }
}

export function percent(part: number, total: number): string {
  return total ? `${((part / total) * 100).toFixed(1)}%` : '0%'
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
  return {
    grid: { left: 8, right: 8, top: 12, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => (typeof value === 'number' ? `${value.toLocaleString()} 条` : '-') },
    xAxis: { type: 'category', data: points.map(point => point.date.slice(5)), ...axisStyle(palette) },
    yAxis: valueAxis('', palette, true),
    series: [{
      name: '采集量',
      type: 'bar',
      barMaxWidth: 8,
      data: points.map(point => ({
        value: point.rows,
        itemStyle: { color: isWeekend(point.date) ? palette.primaryLight : palette.primary },
      })),
    }],
  }
}

export interface HeadlinePart {
  text: string
  strong?: boolean
  tone?: DeltaTone
}

/** 概览顶部的一句话结论：领导不必自己从六张卡片里拼出「整体怎样、变好变坏、该看哪里」。 */
export function headline(overview: CrawlerV2Overview, attention: { newStale: number; dropped: number } | null): HeadlinePart[][] {
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
  if (attention) {
    sentences.push([
      { text: '本周新停更 ' },
      { text: attention.newStale.toLocaleString(), strong: true, tone: attention.newStale ? 'bad' : 'flat' },
      { text: ' 个、采集量骤降 ' },
      { text: attention.dropped.toLocaleString(), strong: true, tone: attention.dropped ? 'bad' : 'flat' },
      { text: ' 个，名单见下方「需要关注」' },
    ])
  }
  const volume = changeText(recent.rows, recent.previous_rows)
  sentences.push([
    { text: `近 ${recent.days} 天采集 ` },
    { text: countText(recent.rows), strong: true },
    { text: `，较前 ${recent.days} 天 ` },
    { text: volume.text, tone: volume.trend === 'up' ? 'good' : volume.trend === 'down' ? 'bad' : 'flat' },
  ])
  return sentences
}

export type ProvinceSort = 'stale' | 'rate' | 'sites'

function staleRate(item: CrawlerProvince): number {
  return item.sites ? item.stale / item.sites : 0
}

/** 全部分类都参与排序，网站少的也不剔除：全国、国央企、港澳和 32 个省是同一套「省份」字段分类。 */
export function sortProvinces(items: CrawlerProvince[], by: ProvinceSort, limit?: number): CrawlerProvince[] {
  const key: Record<ProvinceSort, (item: CrawlerProvince) => number> = { stale: item => item.stale, rate: staleRate, sites: item => item.sites }
  const sorted = [...items].sort((a, b) => key[by](b) - key[by](a) || b.sites - a.sites || a.name.localeCompare(b.name, 'zh'))
  return limit ? sorted.slice(0, limit) : sorted
}

/** 左右各半，两列共用同一个横坐标最大值，条长才能对比。 */
export function provinceColumns(items: CrawlerProvince[]): CrawlerProvince[][] {
  if (!items.length) return []
  const mid = Math.ceil(items.length / 2)
  return [items.slice(0, mid), items.slice(mid)].filter(column => column.length > 0)
}

export function provinceAxisMax(items: CrawlerProvince[]): number {
  return Math.max(1, ...items.map(item => item.sites))
}

export function provinceOption(items: CrawlerProvince[], palette: ChartPalette, axisMax = provinceAxisMax(items)): ChartOption {
  // 横向条形图的类目轴从下往上画，倒过来让排第一的在最上面。
  const rows = [...items].reverse()
  const stack = (name: string, color: string, pick: (item: CrawlerProvince) => number, labeled = false) => ({
    name,
    type: 'bar',
    stack: 'sites',
    barMaxWidth: 16,
    itemStyle: { color },
    data: rows.map(pick),
    label: labeled ? {
      show: true,
      position: 'right',
      color: palette.inkMuted,
      fontSize: 11,
      formatter: (params: { dataIndex: number }) => {
        const stale = rows[params.dataIndex]?.stale ?? 0
        return stale ? String(stale) : ''
      },
    } : { show: false },
  })
  return {
    grid: { left: 4, right: 40, top: 8, bottom: 4, containLabel: true },
    legend: { show: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number }[]) => {
        const item = rows[params[0]?.dataIndex ?? -1]
        if (!item) return ''
        return [
          `<b>${item.name}</b>（共 ${item.sites} 个）`,
          `正常 ${item.normal}　关注 ${item.watch}　停更 ${item.stale}`,
          `停更率 ${percent(item.stale, item.sites)}`,
          item.raw_names.length > 1 ? `含写法：${item.raw_names.map(name => name || '空').join('、')}` : '',
          '点击按该分类筛选下方列表',
        ].filter(Boolean).join('<br/>')
      },
    },
    xAxis: {
      type: 'value',
      max: axisMax,
      axisLabel: { show: false },
      axisLine: { show: false },
      splitLine: { show: false },
    },
    yAxis: { type: 'category', data: rows.map(item => item.name), ...axisStyle(palette) },
    series: [
      stack('正常', palette.success, item => item.normal),
      stack('关注', palette.warning, item => item.watch),
      stack('停更', palette.danger, item => item.stale, true),
    ],
  }
}
