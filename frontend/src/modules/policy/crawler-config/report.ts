import type { ConfigSyncStatus, ConfigWeek } from '@/api/crawlerConfig'
import type { ChartOption, ChartPalette } from '@/components/charts/echarts'

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

/** 每周新增上线（柱）和累计上线（线），两个纵轴。 */
export function weeklyOption(weeks: ConfigWeek[], palette: ChartPalette): ChartOption {
  const axisLabel = { color: palette.inkMuted }
  return {
    grid: { left: 8, right: 8, top: 36, bottom: 4, containLabel: true },
    legend: { top: 0, right: 0, textStyle: { color: palette.inkMuted } },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { dataIndex: number }[]) => {
        const week = weeks[params[0]?.dataIndex ?? -1]
        if (!week) return ''
        return [`<b>${week.week_from} 至 ${week.week_to}</b>`, `新增上线 ${week.new} 个`, `累计上线 ${week.cumulative.toLocaleString()} 个`].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: weeks.map(weekLabel),
      axisLine: { lineStyle: { color: palette.border } },
      axisTick: { show: false },
      axisLabel,
    },
    yAxis: [
      { type: 'value', name: '新增', minInterval: 1, nameTextStyle: axisLabel, axisLabel, splitLine: { lineStyle: { color: palette.border, type: 'dashed' } } },
      { type: 'value', name: '累计', minInterval: 1, nameTextStyle: axisLabel, axisLabel, splitLine: { show: false } },
    ],
    series: [
      {
        name: '新增上线',
        type: 'bar',
        data: weeks.map(week => week.new),
        barMaxWidth: 32,
        itemStyle: { color: palette.primary, borderRadius: [2, 2, 0, 0] },
        label: { show: true, position: 'top', color: palette.ink },
      },
      {
        name: '累计上线',
        type: 'line',
        yAxisIndex: 1,
        data: weeks.map(week => week.cumulative),
        symbolSize: 6,
        itemStyle: { color: palette.success },
        lineStyle: { color: palette.success, width: 2 },
      },
    ],
  }
}
