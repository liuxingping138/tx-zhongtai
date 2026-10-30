import { describe, expect, it } from 'vitest'

import type { OnlineDevice } from '@/api/system'
import { deviceAction, sessionCounts, visibleSessions, windowText } from './sessionView'

function device(userId: string, overrides: Partial<OnlineDevice> = {}): OnlineDevice {
  return {
    id: `${userId}-${Math.random()}`,
    user: { id: userId, username: userId, display_name: userId },
    ip: '10.0.0.1',
    user_agent: '',
    created_at: '2026-10-29T00:00:00Z',
    last_seen_at: '2026-10-30T00:00:00Z',
    online: true,
    current: false,
    can_manage: true,
    ...overrides,
  }
}

describe('在线用户和有效登录分开算', () => {
  const items = [
    device('a'),
    device('a', { online: false }),
    device('b', { online: false }),
    device('c'),
  ]

  it('在线只算 30 分钟内有操作的设备，有效登录算全部', () => {
    expect(sessionCounts(items)).toEqual({ onlinePeople: 2, onlineDevices: 2, validPeople: 3, validDevices: 4 })
  })

  it('「在线」只列在线的设备，「全部有效登录」全列', () => {
    expect(visibleSessions(items, 'online')).toHaveLength(2)
    expect(visibleSessions(items, 'all')).toHaveLength(4)
  })

  it('窗口按接口给的秒数写', () => {
    expect(windowText(1800)).toBe('30 分钟')
    expect(windowText(3600)).toBe('1 小时')
    expect(windowText(undefined)).toBe('30 分钟')
  })
})

describe('每台设备给什么操作', () => {
  it('正在用的这台写「当前设备」，不给下线', () => {
    expect(deviceAction({ current: true, can_manage: false }, true)).toBe('current')
  })

  it('管不了的设备（超级管理员的）和没有管理档时都不给下线', () => {
    expect(deviceAction({ current: false, can_manage: false }, true)).toBe('none')
    expect(deviceAction({ current: false, can_manage: true }, false)).toBe('none')
    expect(deviceAction({ current: false, can_manage: true }, true)).toBe('revoke')
  })
})
