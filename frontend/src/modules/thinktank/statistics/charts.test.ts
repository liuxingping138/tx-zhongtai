import { describe, expect, it } from 'vitest'

import { chartPalette } from '@/components/charts/echarts'
import {
  avatarToneIndex,
  buildConsumeTrendOption,
  buildLibraryDonutOption,
  buildProduceTrendOption,
  formatDelta,
} from './charts'

const palette = chartPalette()

describe('智库统计图表与指标辅助函数', () => {
  it('构造三库环形图配置，并在单库选中时弱化其余扇区', () => {
    const libs = [
      { key: 'knowledge' as const, label: '资料库', files: 1448, defined: 1433, defined_rate: 99, share_pct: 80, size_bytes: 1000, size_display: '1 KB' },
      { key: 'reports' as const, label: '报告库', files: 200, defined: 190, defined_rate: 95, share_pct: 11, size_bytes: 500, size_display: '500 B' },
      { key: 'proposals' as const, label: '方案库', files: 160, defined: 150, defined_rate: 93.8, share_pct: 9, size_bytes: 400, size_display: '400 B' },
    ]
    const opt = buildLibraryDonutOption(libs, 'knowledge', palette) as { series: { data: { itemStyle: { opacity: number } }[] }[] }
    expect(opt.series[0]!.data).toHaveLength(3)
    expect(opt.series[0]!.data[0]!.itemStyle.opacity).toBe(1)
    expect(opt.series[0]!.data[1]!.itemStyle.opacity).toBe(0.25)
  })

  it('构造内容生产与知识消费趋势图的柱线与平滑模式', () => {
    const points = [
      {
        bucket_key: '2026-11-16',
        label: '26 W47',
        knowledge_uploads: 12,
        reports_uploads: 3,
        proposals_uploads: 2,
        total_uploads: 17,
        governance: 24,
        previews: 150,
        downloads: 14,
        active_users: 12,
      },
    ]
    const produceBar = buildProduceTrendOption(points, 'bar', palette) as { series: unknown[] }
    const produceLine = buildProduceTrendOption(points, 'line', palette) as { series: unknown[] }
    const consumeBar = buildConsumeTrendOption(points, 'bar', palette) as { series: unknown[]; yAxis: unknown[] }
    expect(produceBar.series).toHaveLength(4)
    expect(produceLine.series).toHaveLength(2)
    expect(consumeBar.series).toHaveLength(3)
    expect(consumeBar.yAxis).toHaveLength(2)
  })

  it('正确格式化环比变化与稳定头像色号', () => {
    expect(formatDelta(12.34)).toEqual({ text: '↑ 12.3%', tone: 'up' })
    expect(formatDelta(-4.5)).toEqual({ text: '↓ 4.5%', tone: 'down' })
    expect(formatDelta(0)).toEqual({ text: '持平 0.0%', tone: 'flat' })
    expect(formatDelta(null)).toEqual({ text: '全量周期', tone: 'flat' })

    const idx = avatarToneIndex('马丽')
    expect(idx).toBeGreaterThanOrEqual(1)
    expect(idx).toBeLessThanOrEqual(8)
    expect(avatarToneIndex('马丽')).toBe(idx)
  })
})
