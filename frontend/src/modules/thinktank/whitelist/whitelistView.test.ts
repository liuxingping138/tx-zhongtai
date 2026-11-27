import { describe, expect, it } from 'vitest'

import { decisionText, parseBeijing, presetExpiry, remainingText } from './whitelistView'

const NOW = new Date('2026-11-27T08:00:00Z') // 北京时间 16:00

describe('白名单页面文案', () => {
  it('预设时效从现在往后算', () => {
    expect(presetExpiry('7d', NOW)).toBe('2026-12-04T08:00:00.000Z')
    expect(presetExpiry('1d', NOW)).toBe('2026-11-28T08:00:00.000Z')
  })

  it('后端时间按北京时间解析', () => {
    expect(parseBeijing('2026-11-27 16:00:00')?.toISOString()).toBe(NOW.toISOString())
    expect(parseBeijing('')).toBeNull()
    expect(parseBeijing('乱写')).toBeNull()
  })

  it('剩余时间按天、小时、分钟写，过了写已过期', () => {
    expect(remainingText('2026-11-30 16:00:00', NOW)).toBe('还剩 3 天')
    expect(remainingText('2026-11-27 21:30:00', NOW)).toBe('还剩 5 小时')
    expect(remainingText('2026-11-27 16:00:20', NOW)).toBe('还剩 1 分钟')
    expect(remainingText('2026-11-27 15:59:00', NOW)).toBe('已过期')
  })

  it('当前 IP 的判定说清楚凭什么放行', () => {
    expect(decisionText({ ip: '1.119.196.74', allowed: true, via: 'office', expires_at: '' })).toContain('公司网络')
    expect(decisionText({ ip: '8.8.8.8', allowed: true, via: 'whitelist', expires_at: '2026-12-01 10:00:00' })).toContain(
      '2026-12-01 10:00:00',
    )
    expect(decisionText({ ip: '8.8.8.8', allowed: false, via: '', expires_at: '' })).toContain('没有有效白名单')
  })
})
