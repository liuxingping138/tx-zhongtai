import type { ConfigCounts, ConfigProvince, ConfigSyncStatus, ConfigWeek, CrawlerConfigReport } from '@/api/crawlerConfig'
import type { ChartOption, ChartPalette } from '@/components/charts/echarts'

function parseDay(value: string): Date {
  const [year = 0, month = 1, day = 1] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
}

/** ISO 周次（周一开始，含 1 月 4 日的那周是第 1 周），和周选择器显示的一致。 */
export function weekTitle(weekFrom: string): string {
  const thursday = parseDay(weekFrom)
  thursday.setDate(thursday.getDate() + 3 - ((thursday.getDay() + 6) % 7))
  const firstDay = new Date(thursday.getFullYear(), 0, 1)
  const week = 1 + Math.floor((thursday.getTime() - firstDay.getTime()) / 86400000 / 7)
  return `${thursday.getFullYear()} 年第 ${week} 周`
}

/** 「10月19日」 */
export function dayText(value: string): string {
  return `${Number(value.slice(5, 7))}月${Number(value.slice(8, 10))}日`
}

/** 「10月19日 – 10月25日」 */
export function rangeText(from: string, to: string): string {
  return `${dayText(from)} – ${dayText(to)}`
}

/** 「11-02 至 11-08」：趋势图横轴和提示里用，年份在标题里已经有了。 */
export function weekLabel(week: Pick<ConfigWeek, 'week_from' | 'week_to'>): string {
  return `${week.week_from.slice(5)} 至 ${week.week_to.slice(5)}`
}

/** 本周比上周多了几个；上周不在统计范围里时不比。 */
export function deltaText(current: number, previous: number | null): { text: string; tone: 'good' | 'bad' | 'flat' } | null {
  if (previous === null) return null
  const diff = current - previous
  if (diff === 0) return { text: '与上周持平', tone: 'flat' }
  return { text: `较上周 ${diff > 0 ? '+' : ''}${diff}`, tone: diff > 0 ? 'good' : 'bad' }
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

/** 覆盖进度环：已爬蓝色填充、异常砖红、未爬是浅灰底槽。 */
export function coverageOption(totals: ConfigCounts, palette: ChartPalette): ChartOption {
  const other = Math.max(0, totals.total - totals.online - totals.abnormal)
  return {
    tooltip: { trigger: 'item', formatter: '{b}：{c} 个（{d}%）' },
    series: [{
      type: 'pie',
      radius: ['72%', '92%'],
      silent: false,
      avoidLabelOverlap: false,
      label: { show: false },
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      data: [
        { name: '已爬', value: totals.online, itemStyle: { color: palette.primary } },
        { name: '异常', value: totals.abnormal, itemStyle: { color: palette.danger } },
        { name: '未爬及其他', value: other, itemStyle: { color: palette.border } },
      ],
    }],
  }
}

export type ProvinceSort = 'total' | 'new' | 'coverage'

export interface ProvinceBar {
  item: ConfigProvince
  /** 已爬、异常占栏目总数的百分比，剩下的是底槽 */
  online: number
  abnormal: number
  hint: string
}

const SORTERS: Record<ProvinceSort, (a: ConfigProvince, b: ConfigProvince) => number> = {
  total: (a, b) => b.total - a.total,
  new: (a, b) => b.new - a.new || b.total - a.total,
  coverage: (a, b) => a.coverage - b.coverage || b.total - a.total,
}

/** 分省排序：按栏目数从多到少、本周新增从多到少，或覆盖率从低到高（先看落后的省）；没填省份的始终排最后。 */
export function sortProvinces(rows: ConfigProvince[], sort: ProvinceSort): ConfigProvince[] {
  const blank = (row: ConfigProvince) => (row.province_name.startsWith('（') ? 1 : 0)
  return [...rows].sort((a, b) => blank(a) - blank(b) || SORTERS[sort](a, b))
}

/** 每周配置数的底色深浅：0 不着色，其余按占全表最大值的比例，最浅也看得出来。 */
export function heatLevel(value: number, max: number): number {
  if (!value || !max) return 0
  return Math.round((0.15 + (0.85 * value) / max) * 100) / 100
}

/** 分省进度条：每个省已爬、异常占栏目总数的比例。 */
export function provinceBars(rows: ConfigProvince[], sort: ProvinceSort): ProvinceBar[] {
  const sorted = sortProvinces(rows, sort)
  return sorted.map(item => {
    const share = (value: number) => (item.total ? (value * 100) / item.total : 0)
    return {
      item,
      online: share(item.online),
      abnormal: share(item.abnormal),
      hint: `${item.province_name}：栏目 ${item.total} 个，已爬 ${item.online}，未爬 ${item.pending}，异常 ${item.abnormal}，本周新增 ${item.new}`,
    }
  })
}

/** 每周新配置的栏目数，一周一根柱子；累计数在提示框里。 */
export function weeklyOption(weeks: ConfigWeek[], palette: ChartPalette): ChartOption {
  const axisLabel = { color: palette.inkMuted }
  return {
    grid: { left: 8, right: 8, top: 28, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number }[]) => {
        const week = weeks[params[0]?.dataIndex ?? -1]
        if (!week) return ''
        return [`<b>${week.week_from} 至 ${week.week_to}</b>`, `当周新配置 ${week.new} 个`, `累计已配置 ${week.cumulative.toLocaleString()} 个`].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: weeks.map(weekLabel),
      axisLine: { lineStyle: { color: palette.border } },
      axisTick: { show: false },
      axisLabel,
    },
    yAxis: { type: 'value', name: '栏目数', minInterval: 1, nameTextStyle: axisLabel, axisLabel, splitLine: { lineStyle: { color: palette.border, type: 'dashed' } } },
    series: [{
      name: '当周新配置',
      type: 'bar',
      data: weeks.map(week => week.new),
      barMaxWidth: 40,
      itemStyle: { color: palette.success, borderRadius: [3, 3, 0, 0] },
      label: { show: true, position: 'top', color: palette.ink, fontWeight: 600 },
    }],
  }
}

export interface HeadlinePart { text: string; strong?: boolean; tone?: 'good' | 'bad' }

/**
 * 页面最上面给领导的一句话：截至什么时候已配置多少栏目、覆盖多少，本周新增多少，有没有异常。
 * 看往周时「已配置」用那周周末的累计数；统计起点之前的周不谈新增。
 */
export function headline(report: CrawlerConfigReport, current: boolean): HeadlinePart[][] {
  const configured = current ? report.totals.online : (report.trend.at(-1)?.cumulative ?? report.totals.online)
  const asOf = current ? '截至今天' : `截至 ${dayText(report.week_to)}`
  const sentences: HeadlinePart[][] = [[
    { text: `${asOf}，已配置爬虫栏目 ` },
    { text: configured.toLocaleString(), strong: true },
    { text: ' 个' },
    ...(current ? [{ text: `，占信源栏目的 ` }, { text: `${report.totals.coverage}%`, strong: true }] : []),
  ]]
  if (report.counted) {
    const delta = deltaText(report.totals.new, report.previous_new)
    sentences.push([
      { text: '本周新增 ' },
      { text: report.totals.new.toLocaleString(), strong: true },
      { text: ' 个' },
      ...(delta ? [{ text: `，${delta.text}`, tone: delta.tone === 'flat' ? undefined : delta.tone }] : []),
    ])
  } else {
    sentences.push([{ text: `每周新增从 ${dayText(report.report_start)}那周开始统计，之前配置的都算期初存量` }])
  }
  if (report.totals.abnormal) {
    sentences.push([{ text: '有 ' }, { text: report.totals.abnormal.toLocaleString(), strong: true, tone: 'bad' }, { text: ' 个栏目异常待核对' }])
  }
  return sentences
}
