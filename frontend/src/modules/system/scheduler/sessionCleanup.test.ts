import { describe, expect, it } from 'vitest'

import type { ScheduledRun } from '@/api/scheduler'
import { cleanupProgress, cleanupResultText, cleanupRunText } from './sessionCleanup'

const result = { retention_days: 30, tokens_deleted: 12, sessions_deleted: 5, tokens_remaining: 80, sessions_remaining: 20 }

describe('清理失效会话的结果', () => {
  it('写清删了多少、保留多久、还剩多少', () => {
    expect(cleanupResultText(result)).toBe('删除失效会话 5 个、刷新令牌 12 个 · 保留 30 天内的记录 · 剩余会话 20 个')
  })

  it('没有结果时执行记录写失败原因，列表写破折号', () => {
    expect(cleanupRunText({ result: null, error_message: '执行失败（OperationalError）' })).toBe('执行失败（OperationalError）')
    expect(cleanupRunText({ result: null, error_message: null })).toBe('—')
    expect(cleanupProgress(null)).toBe('—')
    expect(cleanupProgress({ result } as ScheduledRun)).toBe('上次清理 5 个会话')
  })
})
