import type { ConfigPeriod, ConfigProvinceCount, ConfigStatusRow, ConfigSyncStatus, ConfigUnit, CrawlerConfigReport } from '@/api/crawlerConfig'
import type { ChartOption, ChartPalette } from '@/components/charts/echarts'
import { provinceShortName } from '../crawler-monitoring/charts'

/** 后端把省份为空的记在这个名下；它不是信源表里的真实省份，不能拿去筛信源管理。 */
export const BLANK_PROVINCE = '（未填省份）'

export const UNITS: { value: ConfigUnit; label: string; name: string }[] = [
  { value: 'week', label: '按周', name: '周' },
  { value: 'month', label: '按月', name: '月' },
  { value: 'quarter', label: '按季度', name: '季度' },
  { value: 'year', label: '按年', name: '年' },
]
const RELATIVE: Record<ConfigUnit, [string, string]> = {
  week: ['本周', '上周'],
  month: ['本月', '上月'],
  quarter: ['本季度', '上季度'],
  year: ['今年', '去年'],
}

const year = (day: string) => Number(day.slice(0, 4))
const month = (day: string) => Number(day.slice(5, 7))
const date = (day: string) => Number(day.slice(8, 10))
/** 「第一季度」 */
const quarter = (day: string) => `第${'一二三四'[Math.floor((month(day) - 1) / 3)]}季度`

/** 「10月19日」 */
export function dayText(value: string): string {
  return `${month(value)}月${date(value)}日`
}

/** 柱图横轴：周用周一「10/19」，月「10月」，季度「第四季度」，年「2026」。月和季度只画今年，不用带年份。 */
export function periodLabel(unit: ConfigUnit, from: string): string {
  if (unit === 'week') return `${month(from)}/${date(from)}`
  if (unit === 'month') return `${month(from)}月`
  if (unit === 'quarter') return quarter(from)
  return String(year(from))
}

/** 一期的完整写法：「10月19日 – 10月25日」「2026年10月」「2026年第四季度」「2026年」。 */
export function periodRange(unit: ConfigUnit, from: string, to: string): string {
  if (unit === 'week') return `${dayText(from)} – ${dayText(to)}`
  if (unit === 'month') return `${year(from)}年${month(from)}月`
  if (unit === 'quarter') return `${year(from)}年${quarter(from)}`
  return `${year(from)}年`
}

/** 还没到的那几期（今年后面的月份、季度）：柱子是 0，点了也没东西看。 */
export function isFuture(report: Pick<CrawlerConfigReport, 'current_from'>, from: string): boolean {
  return from > report.current_from
}

/** 正在看的这期的前一期、后一期（「上一周 / 下一周」按钮用）。按正在看的期找，不是今天所在的期：
 * 默认看上周时按今天找，「上一周」还是上周、「下一周」永远点不了。没到的期不能选。 */
export function adjacentPeriods(
  report: Pick<CrawlerConfigReport, 'periods' | 'period_from' | 'current_from'>,
): { previous?: ConfigPeriod; next?: ConfigPeriod } {
  const index = report.periods.findIndex(item => item.period_from === report.period_from)
  if (index < 0) return {}
  const next = report.periods[index + 1]
  return { previous: report.periods[index - 1], next: next && !isFuture(report, next.period_from) ? next : undefined }
}

/** 所选这期叫什么：当前这期叫「本周 / 本月」，前一期叫「上周 / 上月」，再早的直接写日期。 */
export function periodName(report: Pick<CrawlerConfigReport, 'unit' | 'period_from' | 'period_to' | 'current_from' | 'periods'>): string {
  const [current, previous] = RELATIVE[report.unit]
  if (report.period_from === report.current_from) return current
  // 月、季度画的是全年，当前这期不一定是最后一根柱子，得按它的位置找前一期。
  const index = report.periods.findIndex(item => item.period_from === report.current_from)
  if (index > 0 && report.period_from === report.periods[index - 1]?.period_from) return previous
  return periodRange(report.unit, report.period_from, report.period_to)
}

/** 「较上周 +64」：多了绿、少了红、一样写持平。上一期没有配置时不比。 */
export function deltaText(current: number, previous: number, unit: ConfigUnit): { text: string; tone: 'good' | 'bad' | 'flat' } {
  const name = `上一${UNITS.find(item => item.value === unit)?.name ?? '期'}`
  const diff = current - previous
  if (diff === 0) return { text: `与${name}持平`, tone: 'flat' }
  return { text: `较${name} ${diff > 0 ? '+' : '−'}${Math.abs(diff).toLocaleString()}`, tone: diff > 0 ? 'good' : 'bad' }
}

/** 同步还在排队或执行中。 */
export function syncRunning(status: ConfigSyncStatus | null): boolean {
  return Boolean(status?.active_run)
}

/** 最近一次同步失败时的提示；成功或在跑时不提示。 */
export function syncFailure(status: ConfigSyncStatus | null): string {
  const last = status?.last_run
  if (!last || status?.active_run || last.status !== 'failed') return ''
  return `最近一次同步失败：${last.error_message || '原因未知'}。页面数据停在上次成功同步时。`
}

/** 贴进 Excel、微信就是每周汇报那张「省份 / 配置网站数量 / 总计」，制表符分列。 */
export function provinceTableText(provinces: ConfigProvinceCount[], total: number): string {
  return [['省份', '配置网站数量'], ...provinces.map(row => [row.province_name, row.new]), ['总计', total]]
    .map(row => row.join('\t'))
    .join('\n')
}

/** 六位十六进制颜色转成带透明度的 rgba：只淡化柱子颜色，柱顶数字不跟着变淡。不是六位十六进制的原样返回。 */
export function tint(color: string, alpha: number): string {
  const hex = /^#([0-9a-f]{6})$/i.exec(color.trim())?.[1]
  if (!hex) return color
  const [r, g, b] = [0, 2, 4].map(index => parseInt(hex.slice(index, index + 2), 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function axis(palette: ChartPalette) {
  return { axisLine: { lineStyle: { color: palette.border } }, axisTick: { show: false }, axisLabel: { color: palette.inkMuted } }
}

function valueAxis(palette: ChartPalette) {
  return { type: 'value', minInterval: 1, axisLabel: { color: palette.inkMuted }, splitLine: { lineStyle: { color: palette.border, type: 'dashed' } } }
}

/** 各期配置数量：所选那期实色、其余同色淡化，柱顶小字写数量；还没到的期不提示「点击查看」。 */
export function periodOption(unit: ConfigUnit, periods: ConfigPeriod[], selected: string, current: string, palette: ChartPalette): ChartOption {
  return {
    grid: { left: 4, right: 4, top: 28, bottom: 0, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: tint(palette.primary, 0.06) } },
      formatter: (params: { dataIndex: number }[]) => {
        const item = periods[params[0]?.dataIndex ?? -1]
        if (!item) return ''
        const title = `<b>${periodRange(unit, item.period_from, item.period_to)}</b>`
        if (item.period_from > current) return `${title}<br/>还没到`
        return [title, `配置 ${item.new.toLocaleString()} 个网站`, '点击查看这一期各省'].join('<br/>')
      },
    },
    xAxis: { type: 'category', data: periods.map(item => periodLabel(unit, item.period_from)), ...axis(palette) },
    yAxis: { ...valueAxis(palette), splitNumber: 4 },
    series: [{
      name: '配置网站数量',
      type: 'bar',
      cursor: 'pointer',
      barMaxWidth: 28,
      data: periods.map(item => {
        const picked = item.period_from === selected
        return {
          value: item.new,
          itemStyle: { color: picked ? palette.primary : tint(palette.primary, 0.35), borderRadius: [4, 4, 0, 0] },
          label: { color: picked ? palette.ink : palette.inkMuted, fontWeight: picked ? 600 : 400 },
        }
      }),
      label: { show: true, position: 'top', fontSize: 11, formatter: (item: { value: number }) => (item.value ? item.value.toLocaleString() : '') },
    }],
  }
}

export interface ProvinceRank extends ConfigProvinceCount {
  rank: number
  /** 占这期总数的百分比，「12.5%」。 */
  share: string
  /** 横条长度：数量最多的省占满，其余按比例。 */
  width: string
}

/** 所选这期各省配置排行（后端已按数量从多到少排好）：名次、占比、横条长度。 */
export function provinceRanking(provinces: ConfigProvinceCount[], total: number): ProvinceRank[] {
  const max = Math.max(0, ...provinces.map(item => item.new))
  return provinces.map((item, index) => ({
    ...item,
    rank: index + 1,
    share: total ? `${((item.new / total) * 100).toFixed(1)}%` : '0.0%',
    width: max ? `${Math.max((item.new / max) * 100, 2)}%` : '0%',
  }))
}

/** 分省爬虫状态的三段：已爬用主色、异常红、未爬用主色的浅底，叠成一根柱，柱高就是这个省的信源总数，深色占多少一眼看出覆盖。 */
export const STATUS_SERIES = [
  { key: 'online', name: '已爬', color: (palette: ChartPalette) => palette.primary },
  { key: 'abnormal', name: '异常', color: (palette: ChartPalette) => palette.danger },
  { key: 'pending', name: '未爬', color: (palette: ChartPalette) => tint(palette.primary, 0.18) },
] as const

/** 按信源总数从多到少；省份为空的放最后。 */
export function statusRows(rows: ConfigStatusRow[]): ConfigStatusRow[] {
  return [...rows].sort((a, b) => Number(a.province_name === BLANK_PROVINCE) - Number(b.province_name === BLANK_PROVINCE) || b.total - a.total)
}

export function statusOption(rows: ConfigStatusRow[], palette: ChartPalette): ChartOption {
  return {
    legend: { left: 0, top: 0, itemWidth: 12, itemHeight: 12, textStyle: { color: palette.inkMuted } },
    grid: { left: 4, right: 4, top: 40, bottom: 0, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: tint(palette.primary, 0.06) } },
      formatter: (params: { dataIndex: number }[]) => {
        const row = rows[params[0]?.dataIndex ?? -1]
        if (!row) return ''
        const share = row.total ? ((row.online / row.total) * 100).toFixed(1) : '0.0'
        return [
          `<b>${row.province_name}</b>（共 ${row.total.toLocaleString()} 个）`,
          `已爬 ${row.online.toLocaleString()}　未爬 ${row.pending.toLocaleString()}　异常 ${row.abnormal.toLocaleString()}`,
          `覆盖率 ${share}%`,
        ].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: rows.map(row => provinceShortName(row.province_name)),
      ...axis(palette),
      // 中文竖排，三十多个省挤在一行也不重叠，和爬虫监测的省份分布一样。
      axisLabel: { color: palette.inkMuted, interval: 0, lineHeight: 13, formatter: (name: string) => name.split('').join('\n') },
    },
    yAxis: { ...valueAxis(palette), splitNumber: 4 },
    series: STATUS_SERIES.map(series => ({
      name: series.name,
      type: 'bar',
      stack: 'status',
      barMaxWidth: 22,
      itemStyle: { color: series.color(palette), borderRadius: series.key === 'pending' ? [4, 4, 0, 0] : 0 },
      data: rows.map(row => row[series.key]),
      // 柱顶写已爬数量（最上面一段负责写，才落在整根柱子顶上）。
      label: series.key === 'pending'
        ? { show: true, position: 'top', fontSize: 11, color: palette.primary, fontWeight: 600, formatter: (params: { dataIndex: number }) => (rows[params.dataIndex]?.online ?? 0).toLocaleString() }
        : { show: false },
    })),
  }
}

