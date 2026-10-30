import { describe, expect, it } from 'vitest'

import type { ManagedUser } from '@/api/system'
import { canManageRow, mergeUserRow, openLabel } from './userRows'

function row(overrides: Partial<ManagedUser> = {}): ManagedUser {
  return {
    id: 'u1',
    username: 'zhangsan',
    display_name: '张三',
    phone: '',
    email: '',
    status: 'active',
    must_change_password: false,
    last_login_at: null,
    last_login_ip: '',
    version: 1,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    roles: [{ id: 'r1', name: '编辑', status: 'active', is_builtin: false }],
    ...overrides,
  }
}

describe('用户列表一行能给哪些操作', () => {
  it('不是超级管理员的看超级管理员那行：不给停用、删除、重置密码、下线', () => {
    expect(canManageRow(row({ can_manage: false }), true)).toBe(false)
    expect(canManageRow(row({ can_manage: true }), true)).toBe(true)
    expect(canManageRow(row({ can_manage: true }), false)).toBe(false)
  })

  it('旧接口没带 can_manage 时照常给，交给后端拒绝', () => {
    expect(canManageRow(row(), true)).toBe(true)
  })

  it('管不了的行只能「查看」', () => {
    expect(openLabel(row({ can_manage: false }), { edit: true, grant: false })).toBe('查看')
    expect(openLabel(row({ can_manage: true }), { edit: true, grant: false })).toBe('编辑')
    expect(openLabel(row({ roles: [] }), { edit: false, grant: true })).toBe('分配角色')
    expect(openLabel(row(), { edit: false, grant: false })).toBe('查看')
  })
})

describe('详情里存好后合进列表那一行', () => {
  it('单独授权存好后「+单独授权」标签跟着变', () => {
    const first = row({ direct_grant_count: 0 })
    const second = row({ id: 'u2', username: 'lisi' })
    const [merged, untouched] = mergeUserRow([first, second], { ...first, version: 2, direct_grant_count: 3 })
    expect(merged?.direct_grant_count).toBe(3)
    expect(merged?.version).toBe(2)
    expect(untouched).toBe(second)
  })

  it('存基本信息时详情不带单独授权数，列表上的标签不被抹掉', () => {
    const detail = row({ display_name: '张三丰', version: 2 })
    delete detail.direct_grant_count
    const [merged] = mergeUserRow([row({ direct_grant_count: 2 })], detail)
    expect(merged?.display_name).toBe('张三丰')
    expect(merged?.direct_grant_count).toBe(2)
  })
})
