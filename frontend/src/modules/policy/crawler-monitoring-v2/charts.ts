import type {
  CrawlerHealth,
  CrawlerProvince,
  CrawlerTrendDays,
  CrawlerTrendPoint,
  SiteStatus,
} from '@/api/crawlerMonitoringV2'
import type { ChartOption, ChartPalette } from '@/components/charts/echarts'

const MOVING_WINDOW = 7
/** 按停更率排序时，网站太少的省份一两个停更就是 100%，排在最前没有意义。 */
export const RATE_MIN_SITES = 20
export const PROVINCE_LIMIT = 15

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

export function trendSummary(points: CrawlerTrendPoint[], days: CrawlerTrendDays): string {
  if (!points.length) return '所选时间范围内没有采集数据'
  const total = points.reduce((sum, point) => sum + point.rows, 0)
  const peak = points.reduce((best, point) => (point.rows > best.rows ? point : best))
  const unit = days === 365 ? '周' : '天'
  return `近 ${days} 天共采集 ${total.toLocaleString()} 条，最高的一${unit}是 ${peak.date}，${peak.rows.toLocaleString()} 条`
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
  const weekly = days === 365
  const points = weekly ? weeklyPoints(raw) : raw
  const bars = points.map(point => ({
    value: point.rows,
    itemStyle: { color: !weekly && isWeekend(point.date) ? palette.primaryLight : palette.primary },
  }))
  const series: Record<string, unknown>[] = [
    { name: weekly ? '每周采集量' : '每日采集量', type: 'bar', data: bars, barMaxWidth: 16 },
    {
      name: weekly ? '日均出数网站' : '出数网站',
      type: 'line',
      yAxisIndex: 1,
      data: points.map(point => point.sites),
      showSymbol: false,
      lineStyle: { type: 'dashed', width: 1.5, color: palette.success },
      itemStyle: { color: palette.success },
    },
  ]
  if (!weekly) {
    series.splice(1, 0, {
      name: '7 日均值',
      type: 'line',
      data: movingAverage(points.map(point => point.rows)),
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2, color: palette.ink },
      itemStyle: { color: palette.ink },
    })
  }
  return {
    grid: { left: 8, right: 8, top: 40, bottom: 4, containLabel: true },
    legend: { top: 0, right: 0, itemWidth: 14, itemHeight: 8, textStyle: { color: palette.inkMuted } },
    tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => (typeof value === 'number' ? value.toLocaleString() : '-') },
    xAxis: { type: 'category', data: points.map(point => (weekly ? `${point.date.slice(5)} 周` : point.date.slice(5))), ...axisStyle(palette) },
    yAxis: [valueAxis('条数', palette, true), valueAxis('网站数', palette, false)],
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
      radius: ['62%', '88%'],
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

export type ProvinceSort = 'stale' | 'rate' | 'sites'

function staleRate(item: CrawlerProvince): number {
  return item.sites ? item.stale / item.sites : 0
}

export function sortProvinces(items: CrawlerProvince[], by: ProvinceSort, limit = PROVINCE_LIMIT): CrawlerProvince[] {
  const pool = by === 'rate' ? items.filter(item => item.sites >= RATE_MIN_SITES) : [...items]
  const key: Record<ProvinceSort, (item: CrawlerProvince) => number> = { stale: item => item.stale, rate: staleRate, sites: item => item.sites }
  return pool.sort((a, b) => key[by](b) - key[by](a) || b.sites - a.sites).slice(0, limit)
}

export function provinceOption(items: CrawlerProvince[], palette: ChartPalette): ChartOption {
  // 横向条形图的类目轴从下往上画，倒过来让排第一的在最上面。
  const rows = [...items].reverse()
  const stack = (name: string, color: string, pick: (item: CrawlerProvince) => number) => ({
    name, type: 'bar', stack: 'sites', barMaxWidth: 14, itemStyle: { color }, data: rows.map(pick),
  })
  return {
    grid: { left: 8, right: 16, top: 32, bottom: 4, containLabel: true },
    legend: { top: 0, right: 0, itemWidth: 14, itemHeight: 8, textStyle: { color: palette.inkMuted } },
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
          '点击按该省份筛选下方列表',
        ].filter(Boolean).join('<br/>')
      },
    },
    xAxis: { type: 'value', axisLabel: { color: palette.inkMuted }, splitLine: { lineStyle: { color: palette.border, type: 'dashed' } } },
    yAxis: { type: 'category', data: rows.map(item => item.name), ...axisStyle(palette) },
    series: [
      stack('正常', palette.success, item => item.normal),
      stack('关注', palette.warning, item => item.watch),
      stack('停更', palette.danger, item => item.stale),
    ],
  }
}
