import { describe, expect, it } from 'vitest'

import { decisionText, expiryDate, expiryError, formatBeijing, parseBeijing, remainingText, type ExpiryForm } from './whitelistView'

const NOW = new Date('2026-11-27T08:00:00Z') // 北京时间 16:00

function form(overrides: Partial<ExpiryForm>): ExpiryForm {
  return { choice: '2h', amount: null, unit: 'hour', datetime: '', current: '', ...overrides }
}

describe('白名单有效期', () => {
  it('常用时长从现在往后算，有 2 小时、4 小时', () => {
    expect(formatBeijing(expiryDate(form({ choice: '2h' }), NOW)!)).toBe('2026-11-27 18:00')
    expect(formatBeijing(expiryDate(form({ choice: '4h' }), NOW)!)).toBe('2026-11-27 20:00')
    expect(formatBeijing(expiryDate(form({ choice: '7d' }), NOW)!)).toBe('2026-12-04 16:00')
  })

  it('自定义时长按小时或天算', () => {
    expect(formatBeijing(expiryDate(form({ choice: 'duration', amount: 5, unit: 'hour' }), NOW)!)).toBe('2026-11-27 21:00')
    expect(formatBeijing(expiryDate(form({ choice: 'duration', amount: 45, unit: 'day' }), NOW)!)).toBe('2027-01-11 16:00')
    expect(expiryError(form({ choice: 'duration', amount: null }), 365, NOW)).toBe('请填写时长')
  })

  it('指定到期时间按北京时间，至少 10 分钟以后、不超过上限', () => {
    expect(expiryError(form({ choice: 'datetime', datetime: '2026-11-27 18:30:00' }), 365, NOW)).toBe('')
    expect(expiryError(form({ choice: 'datetime', datetime: '2026-11-27 16:05:00' }), 365, NOW)).toContain('10 分钟')
    expect(expiryError(form({ choice: 'datetime', datetime: '' }), 365, NOW)).toBe('请选择到期时间')
    expect(expiryError(form({ choice: 'duration', amount: 40, unit: 'day' }), 30, NOW)).toBe('一次最多开通 30 天')
  })

  it('修改时保持原到期时间，已过期的要重新选', () => {
    expect(expiryError(form({ choice: 'keep', current: '2026-11-28 10:00:00' }), 365, NOW)).toBe('')
    expect(expiryError(form({ choice: 'keep', current: '2026-11-27 10:00:00' }), 365, NOW)).toContain('已过')
  })
})

describe('白名单页面文案', () => {
  it('后端时间按北京时间解析', () => {
    expect(parseBeijing('2026-11-27 16:00:00')?.toISOString()).toBe(NOW.toISOString())
    expect(parseBeijing('乱写')).toBeNull()
  })

  it('剩余时间按天、小时、分钟写，过了写已过期', () => {
    expect(remainingText('2026-11-30 16:00:00', NOW)).toBe('还剩 3 天')
    expect(remainingText('2026-11-27 18:00:00', NOW)).toBe('还剩 2 小时')
    expect(remainingText('2026-11-27 16:00:20', NOW)).toBe('还剩 1 分钟')
    expect(remainingText('2026-11-27 15:59:00', NOW)).toBe('已过期')
  })

  it('当前 IP 的判定说清楚凭什么放行', () => {
    expect(decisionText({ ip: '1.119.196.74', allowed: true, via: 'office', expires_at: '' }, '智库')).toContain('公司网络')
    expect(decisionText({ ip: '8.8.8.8', allowed: false, via: '', expires_at: '' }, '智库')).toContain('打不开智库')
  })
})
