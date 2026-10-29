import { describe, expect, it } from 'vitest'

import { browserOf, lockText, loginResult, sinceText } from './loginText'

const MAC_CHROME = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
const WIN_EDGE = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 Edg/130.0'
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'

describe('登录相关的说法', () => {
  it('浏览器和系统', () => {
    expect(browserOf(MAC_CHROME)).toBe('Chrome · macOS')
    expect(browserOf(WIN_EDGE)).toBe('Edge · Windows')
    expect(browserOf(IPHONE)).toBe('Safari · iOS')
    expect(browserOf('')).toBe('—')
    expect(browserOf('curl/8.0')).toBe('curl/8.0')
  })

  it('多久以前', () => {
    const now = new Date('2026-10-29T06:30:00Z')
    expect(sinceText('2026-10-29T06:29:40Z', now)).toBe('刚刚')
    expect(sinceText('2026-10-29T06:27:00Z', now)).toBe('3 分钟前')
    expect(sinceText('2026-10-29T02:50:00Z', now)).toBe('今天 10:50')
    expect(sinceText('2026-10-28T09:28:00Z', now)).toBe('10-28 17:28')
    expect(sinceText('2025-12-30T09:28:00Z', now)).toBe('2025-12-30 17:28')
    expect(sinceText(null, now)).toBe('—')
  })

  it('锁定剩余时间按分钟向上取整', () => {
    expect(lockText(241)).toBe('已锁定，5 分钟后自动解锁')
    expect(lockText(20)).toBe('已锁定，1 分钟后自动解锁')
  })

  it('登录日志的结果', () => {
    expect(loginResult({ action_code: 'login', outcome: 'success', error_code: null })).toEqual({ tone: 'ok', text: '登录成功' })
    expect(loginResult({ action_code: 'login', outcome: 'failure', error_code: 'locked' }).text).toBe('失败：输错次数过多，已锁定')
    expect(loginResult({ action_code: 'login', outcome: 'failure', error_code: 'unauthenticated' }).tone).toBe('bad')
    expect(loginResult({ action_code: 'logout', outcome: 'success', error_code: null }).text).toBe('退出登录')
  })
})
