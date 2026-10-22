import { describe, expect, it } from 'vitest'

import { formatYuan, runStatusText, runStatusType } from './aiTagging'

describe('政策 AI 打标', () => {
  it('金额到分，试跑的小额保留 4 位', () => {
    expect([formatYuan('12.345'), formatYuan('0.0031'), formatYuan(0), formatYuan(null)]).toEqual(['¥12.35', '¥0.0031', '¥0.00', '¥0.00'])
    expect(formatYuan('abc')).toBe('—')
  })

  it('状态写中文，不认识的原样显示', () => {
    expect([runStatusText('running'), runStatusText('failed'), runStatusText('other')]).toEqual(['执行中', '失败', 'other'])
    expect([runStatusType('success'), runStatusType('other')]).toEqual(['success', 'info'])
  })
})
