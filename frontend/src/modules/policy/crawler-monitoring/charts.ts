import type {
  CrawlerOverviewData,
  CrawlerHealth,
  CrawlerProvince,
  CrawlerTrendDays,
  CrawlerTrendPoint,
  SiteStatus,
} from '@/api/crawlerMonitoring'
import type { ChartOption, ChartPalette } from '@/components/charts/echarts'
import { compactCount } from './filters'

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

export function trendOption(raw: CrawlerTrendPoint[], days: CrawlerTrendDays, palette: ChartPalette): ChartOption {
  const buckets = trendBuckets(raw, days)
  const unit = trendUnit(days)
  const daily = unit === 'day'
  return {
    grid: { left: 8, right: 8, top: 28, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number }[]) => {
        const bucket = buckets[params[0]?.dataIndex ?? -1]
        if (!bucket) return ''
        if (daily) return `<b>${bucket.start}${isWeekend(bucket.start) ? '（周末）' : ''}</b><br/>采集 ${bucket.rows.toLocaleString()} 条`
        const title = unit === 'month' ? bucket.start.slice(0, 7) : `${bucket.start} 起一周`
        return [`<b>${title}</b>`, `日均 ${bucket.average.toLocaleString()} 条`, `共 ${bucket.rows.toLocaleString()} 条（${bucket.days} 天）`].join('<br/>')
      },
    },
    xAxis: { type: 'category', data: buckets.map(bucket => bucket.label), ...axisStyle(palette) },
    yAxis: valueAxis(daily ? '条数' : '日均条数', palette, true),
    series: [{
      name: daily ? '每日采集量' : `每${unit === 'month' ? '月' : '周'}日均采集量`,
      type: 'bar',
      data: buckets.map(bucket => bucket.average),
      barMaxWidth: 28,
      itemStyle: { color: palette.primary, borderRadius: [2, 2, 0, 0] },
    }],
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

export function healthOption(slices: HealthSlice[], palette: ChartPalette): ChartOption {
  return {
    tooltip: { trigger: 'item', formatter: '{b}：{c} 个（{d}%）' },
    series: [{
      type: 'pie',
      radius: ['54%', '90%'],
      avoidLabelOverlap: false,
      label: { show: false },
      itemStyle: { borderColor: palette.surface, borderWidth: 2 },
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

/** 按网站总数从多到少，同数再按停更数；全部分类都保留，网站少的也不剔除：全国、国央企和 31 个省是同一套「省份」字段分类。 */
export function sortProvinces(items: CrawlerProvince[], limit?: number): CrawlerProvince[] {
  const sorted = [...items].sort((a, b) => b.sites - a.sites || b.stale - a.stale || a.name.localeCompare(b.name, 'zh'))
  return limit ? sorted.slice(0, limit) : sorted
}

export interface ProvinceTile {
  item: CrawlerProvince
  /** 「共 466 个 · 停更 89%」；没有网站时写「暂无网站」 */
  caption: string
  /** 比例条三段宽度（百分比），没有网站时全为 0 */
  shares: { normal: number; watch: number; stale: number }
  /** 悬停提示：各状态数量和合并前的写法 */
  hint: string
}

export function provinceTile(item: CrawlerProvince): ProvinceTile {
  const share = (value: number) => (item.sites ? (value / item.sites) * 100 : 0)
  return {
    item,
    caption: item.sites ? `共 ${item.sites.toLocaleString()} 个 · 停更 ${percent(item.stale, item.sites)}` : '暂无网站',
    shares: { normal: share(item.normal), watch: share(item.watch), stale: share(item.stale) },
    hint: [
      `正常 ${item.normal}　关注 ${item.watch}　停更 ${item.stale}`,
      item.raw_names.length > 1 ? `含写法：${item.raw_names.map(name => name || '空').join('、')}` : '',
    ].filter(Boolean).join('\n'),
  }
}

/** 下方明细已按这个分类的全部原始写法筛选时，柱子和卡片显示为选中。 */
export function provinceSelected(item: CrawlerProvince, applied: string[]): boolean {
  return applied.length > 0 && [...applied].sort().join('|') === [...item.raw_names].sort().join('|')
}

/** 横轴放不下「新疆维吾尔自治区」，用简称；全国、国央企等原样。完整名称在提示框里。 */
export function provinceShortName(name: string): string {
  return name.replace(/(壮族|回族|维吾尔)?自治区$|特别行政区$|[省市]$/, '') || name
}

/** 每个分类一根柱：柱高是网站总数，其中停更的部分用红色叠在底部，一根柱子看清规模和停更多少。 */
export const PROVINCE_SERIES = [
  { name: '网站总数', value: (item: CrawlerProvince) => item.sites, color: (palette: ChartPalette) => palette.primary },
  { name: '停更网站数', value: (item: CrawlerProvince) => item.stale, color: (palette: ChartPalette) => palette.danger },
] as const

export function provinceOption(items: CrawlerProvince[], palette: ChartPalette, selected: string[] = []): ChartOption {
  const picked = items.findIndex(item => provinceSelected(item, selected))
  return {
    legend: { left: 0, top: 0, itemWidth: 12, itemHeight: 12, textStyle: { color: palette.inkMuted } },
    grid: { left: 8, right: 8, top: 48, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number }[]) => {
        const item = items[params[0]?.dataIndex ?? -1]
        if (!item) return ''
        if (!item.sites) return `<b>${item.name}</b><br/>暂无网站`
        return [
          `<b>${item.name}</b>（共 ${item.sites} 个）`,
          `正常 ${item.normal}　关注 ${item.watch}　停更 ${item.stale}`,
          `停更率 ${percent(item.stale, item.sites)}`,
          item.raw_names.length > 1 ? `含写法：${item.raw_names.map(name => name || '空').join('、')}` : '',
          '点击筛选下方列表',
        ].filter(Boolean).join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: items.map(item => provinceShortName(item.name)),
      ...axisStyle(palette),
      // 中文竖排，38 个分类挤在一行也不会重叠。
      axisLabel: { color: palette.inkMuted, interval: 0, lineHeight: 13, formatter: (name: string) => name.split('').join('\n') },
    },
    yAxis: valueAxis('网站数', palette, true),
    series: PROVINCE_SERIES.map(series => ({
      name: series.name,
      type: 'bar',
      color: series.color(palette),
      barMaxWidth: 22,
      // 两个系列完全重叠：停更画在网站总数前面，看起来是一根两色的柱子。
      barGap: '-100%',
      // 选中一个分类时其余变淡，和卡片、健康图的选中态一样明确。
      data: items.map((item, index) => ({
        value: series.value(item),
        itemStyle: { color: series.color(palette), opacity: picked < 0 || picked === index ? 1 : 0.3, borderRadius: [2, 2, 0, 0] },
      })),
      // 柱顶只写网站总数；停更数和停更率在悬停提示里。
      label: {
        show: series.name === '网站总数',
        position: 'top',
        color: palette.ink,
        fontSize: 11,
        formatter: (params: { dataIndex: number }) => {
          const item = items[params.dataIndex]
          return item?.sites ? String(series.value(item)) : ''
        },
      },
    })),
  }
}
