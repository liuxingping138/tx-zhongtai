import { describe, expect, it } from 'vitest'

import {
  DEFAULT_RANGE_TIME,
  beijingDate,
  formatTime,
  isFutureBeijingDate,
  localCalendarDate,
  localCalendarYmd,
  toBeijingIso,
} from './time'

describe('formatTime', () => {
  it('把 UTC 转成北京时间', () => {
    expect(formatTime('2026-09-18T07:36:08.075954+00:00')).toBe('2026-09-18 15:36:08')
    expect(formatTime('2026-09-18T07:36:08Z')).toBe('2026-09-18 15:36:08')
  })

  it('已经是北京时间的字符串原样返回', () => {
    expect(formatTime('2026-09-18 15:36:08')).toBe('2026-09-18 15:36:08')
  })

  it('筛选时间补上北京时区', () => {
    expect(toBeijingIso('2026-09-18T15:00:00')).toBe('2026-09-18T15:00:00+08:00')
    expect(toBeijingIso('2026-09-18T07:00:00Z')).toBe('2026-09-18T07:00:00Z')
    expect(toBeijingIso('')).toBe('')
  })

  it('空值显示短横', () => {
    expect(formatTime('')).toBe('-')
    expect(formatTime(null)).toBe('-')
  })

  it('按北京时间判定今日与未来日期，跨零点 00:00–08:00 不误禁北京当日', () => {
    expect(DEFAULT_RANGE_TIME[0].getHours()).toBe(0)
    expect(DEFAULT_RANGE_TIME[1].getHours()).toBe(23)
    expect(DEFAULT_RANGE_TIME[1].getMinutes()).toBe(59)
    expect(DEFAULT_RANGE_TIME[1].getSeconds()).toBe(59)

    // 2026-11-11T18:00:00Z = 北京时间 2026-11-12 02:00:00
    const beijingEarlyMorning = new Date('2026-11-11T18:00:00Z')
    expect(beijingDate(beijingEarlyMorning)).toBe('2026-11-12')
    expect(beijingDate()).toMatch(/^\d{4}-\d{2}-\d{2}$/)

    const day12 = localCalendarDate('2026-11-12')
    const day13 = localCalendarDate('2026-11-13')
    expect(localCalendarYmd(day12)).toBe('2026-11-12')
    expect(isFutureBeijingDate(day12, beijingEarlyMorning)).toBe(false)
    expect(isFutureBeijingDate(day13, beijingEarlyMorning)).toBe(true)
    expect(isFutureBeijingDate(localCalendarDate('2099-01-01'))).toBe(true)
  })
})
