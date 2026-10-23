import type { ConfigSyncStatus, ConfigWeek } from '@/api/crawlerConfig'
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

/** 「10-19」：趋势图横轴，一周用周一表示。 */
export function weekLabel(week: Pick<ConfigWeek, 'week_from'>): string {
  return week.week_from.slice(5)
}

/** 本周比上周多了几个。 */
export function deltaText(current: number, previous: number): { text: string; tone: 'good' | 'bad' | 'flat' } {
  const diff = current - previous
  if (diff === 0) return { text: '与上周持平', tone: 'flat' }
  return { text: `较上周 ${diff > 0 ? '+' : ''}${diff.toLocaleString()}`, tone: diff > 0 ? 'good' : 'bad' }
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

/** 有数据的周少于两周时柱图没有可比的，不画。 */
export function trendWorthShowing(weeks: ConfigWeek[]): boolean {
  return weeks.filter(week => week.new > 0).length >= 2
}

/** 近 12 周每周配置数量：所选那周（最后一根）用实色，其余淡一些；累计在提示框里。 */
export function weeklyOption(weeks: ConfigWeek[], palette: ChartPalette): ChartOption {
  const axisLabel = { color: palette.inkMuted }
  const last = weeks.length - 1
  return {
    grid: { left: 8, right: 8, top: 24, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number }[]) => {
        const week = weeks[params[0]?.dataIndex ?? -1]
        if (!week) return ''
        return [`<b>${week.week_from} 至 ${week.week_to}</b>`, `配置 ${week.new.toLocaleString()} 个网站`, `截至周末累计 ${week.cumulative.toLocaleString()} 个`, '点击查看这一周'].join('<br/>')
      },
    },
    xAxis: { type: 'category', data: weeks.map(weekLabel), axisLine: { lineStyle: { color: palette.border } }, axisTick: { show: false }, axisLabel },
    yAxis: { type: 'value', minInterval: 1, axisLabel, splitLine: { lineStyle: { color: palette.border, type: 'dashed' } } },
    series: [{
      name: '配置网站数量',
      type: 'bar',
      cursor: 'pointer',
      barMaxWidth: 36,
      data: weeks.map((week, index) => ({
        value: week.new,
        itemStyle: { color: palette.success, opacity: index === last ? 1 : 0.45, borderRadius: [3, 3, 0, 0] },
      })),
      label: { show: true, position: 'top', color: palette.ink, formatter: (item: { value: number }) => (item.value ? String(item.value) : '') },
    }],
  }
}

/** 分省表「近 12 周」小柱：按这一行的最大值折算高度（百分比），没配置的周留一条底线。 */
export function sparkHeights(values: number[]): number[] {
  const max = Math.max(0, ...values)
  return values.map(value => (value && max ? Math.max(8, Math.round((value * 100) / max)) : 0))
}
