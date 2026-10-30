import { describe, expect, it } from 'vitest'

import { auditCleanupProgress, auditCleanupResultText, auditCleanupRunText } from './auditCleanup'

describe('清理到期操作日志', () => {
  it('写出删了多少条、保留几天；原来落到爬虫的写法显示「—」，看着像什么都没删', () => {
    expect(auditCleanupResultText({ deleted: 1200, retention_days: 180 })).toBe('删除到期操作日志 1200 条 · 保留 180 天内的记录')
    expect(auditCleanupProgress({ result: { deleted: 0, retention_days: 180 } } as never)).toBe('上次删除 0 条')
  })

  it('失败写原因，没跑过写横线', () => {
    expect(auditCleanupRunText({ result: null, error_message: '没有配置清理账号连接' })).toBe('没有配置清理账号连接')
    expect(auditCleanupProgress(null)).toBe('—')
  })
})
