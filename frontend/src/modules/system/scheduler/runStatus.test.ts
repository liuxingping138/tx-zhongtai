import { describe, expect, it } from 'vitest'

import { duration, statusType } from './runStatus'

describe('statusType', () => {
  it('成功绿、失败红、等待重试橙，其余灰', () => {
    expect(statusType('success')).toBe('success')
    expect(statusType('failed')).toBe('danger')
    expect(statusType('retrying')).toBe('warning')
    expect(statusType('running')).toBe('info')
    expect(statusType(undefined)).toBe('info')
  })
})

describe('duration', () => {
  const at = (iso: string | null) => iso
  it('没开始或没结束显示破折号', () => {
    expect(duration({ started_at: null, finished_at: at('2026-10-10T01:00:00Z') })).toBe('—')
    expect(duration({ started_at: at('2026-10-10T01:00:00Z'), finished_at: null })).toBe('—')
  })
  it('一分钟以内按秒，之后按分秒', () => {
    expect(duration({ started_at: '2026-10-10T01:00:00Z', finished_at: '2026-10-10T01:00:42Z' })).toBe('42 秒')
    expect(duration({ started_at: '2026-10-10T01:00:00Z', finished_at: '2026-10-10T01:03:05Z' })).toBe('3 分 5 秒')
  })
  it('结束早于开始时不出现负数', () => {
    expect(duration({ started_at: '2026-10-10T01:00:10Z', finished_at: '2026-10-10T01:00:00Z' })).toBe('0 秒')
  })
})
