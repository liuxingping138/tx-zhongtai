import type { ConfigCounts, ConfigProvince, ConfigSyncStatus, ConfigWeek } from '@/api/crawlerConfig'
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

/** 覆盖进度环：已配置蓝色填充、异常砖红、未配置是浅灰底槽。 */
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
        { name: '已配置', value: totals.online, itemStyle: { color: palette.primary } },
        { name: '异常', value: totals.abnormal, itemStyle: { color: palette.danger } },
        { name: '未配置', value: other, itemStyle: { color: palette.border } },
      ],
    }],
  }
}

/** 每周配置数的底色深浅：0 不着色，其余按占全表最大值的比例，最浅也看得出来。 */
export function heatLevel(value: number, max: number): number {
  if (!value || !max) return 0
  return Math.round((0.15 + (0.85 * value) / max) * 100) / 100
}

/** 本周各省配置网站数量：只列有配置的省，按数量从多到少；条长按最多的那个省折算。 */
export function weekProvinces(rows: ConfigProvince[]): { name: string; count: number; share: number }[] {
  const picked = rows.filter(row => row.new > 0).sort((a, b) => b.new - a.new)
  const max = picked[0]?.new ?? 0
  return picked.map(row => ({ name: row.province_name, count: row.new, share: max ? (row.new * 100) / max : 0 }))
}

/** 每周新配置的网站数，一周一根柱子；累计数在提示框里。 */
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
        return [`<b>${week.week_from} 至 ${week.week_to}</b>`, `当周配置 ${week.new} 个`, `累计已配置 ${week.cumulative.toLocaleString()} 个`].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: weeks.map(weekLabel),
      axisLine: { lineStyle: { color: palette.border } },
      axisTick: { show: false },
      axisLabel,
    },
    yAxis: { type: 'value', name: '网站数', minInterval: 1, nameTextStyle: axisLabel, axisLabel, splitLine: { lineStyle: { color: palette.border, type: 'dashed' } } },
    series: [{
      name: '当周配置',
      type: 'bar',
      data: weeks.map(week => week.new),
      barMaxWidth: 40,
      itemStyle: { color: palette.success, borderRadius: [3, 3, 0, 0] },
      label: { show: true, position: 'top', color: palette.ink, fontWeight: 600 },
    }],
  }
}
