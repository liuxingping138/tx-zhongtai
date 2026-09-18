import { describe, expect, it } from 'vitest'

import { formatTime } from './time'

describe('formatTime', () => {
  it('把 UTC 转成北京时间', () => {
    expect(formatTime('2026-09-18T07:36:08.075954+00:00')).toBe('2026-09-18 15:36:08')
    expect(formatTime('2026-09-18T07:36:08Z')).toBe('2026-09-18 15:36:08')
  })

  it('已经是北京时间的字符串原样返回', () => {
    expect(formatTime('2026-09-18 15:36:08')).toBe('2026-09-18 15:36:08')
  })

  it('空值显示短横', () => {
    expect(formatTime('')).toBe('-')
    expect(formatTime(null)).toBe('-')
  })
})
