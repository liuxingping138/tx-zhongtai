import { describe, expect, it } from 'vitest'

import { ROUTE_BY_NAME } from '@/router/menu'
import { ENTRY_DESCRIPTIONS } from './workspace'

// 已并入「角色与权限」、只做跳转的旧路由，不出现在菜单和查找里。
const REDIRECT_ONLY = new Set(['/system/permissions'])

describe('查找模块里的用途说明', () => {
  it('每个菜单入口都有自己的说明，不退回「进入业务模块」', () => {
    const missing = Object.values(ROUTE_BY_NAME).filter(path => !REDIRECT_ONLY.has(path) && !ENTRY_DESCRIPTIONS[path])
    expect(missing).toEqual([])
  })

  it('在线用户、登录日志写的是它们自己的用途', () => {
    expect(ENTRY_DESCRIPTIONS['/system/sessions']).toContain('在线')
    expect(ENTRY_DESCRIPTIONS['/system/login-logs']).toContain('登录')
  })
})
