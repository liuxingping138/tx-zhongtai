import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  deleteUser: vi.fn<(id: string) => Promise<unknown>>(),
  resetUserPassword: vi.fn<(id: string) => Promise<{ temporary_password: string }>>(),
  revokeUserSessions: vi.fn<(id: string) => Promise<{ revoked: number }>>(),
  updateUser: vi.fn<(id: string, body: unknown) => Promise<unknown>>(),
}))
const ui = vi.hoisted(() => ({
  confirm: vi.fn<() => Promise<unknown>>(),
  success: vi.fn(),
  error: vi.fn(),
}))
vi.mock('@/api/system', () => api)
vi.mock('element-plus', () => ({ ElMessage: { success: ui.success, error: ui.error }, ElMessageBox: { confirm: ui.confirm } }))

import type { UserItem } from '@/api/types'
import { useUserActions } from './useUserActions'

const user = { id: 'u1', username: 'zhangsan', status: 'active', version: 4 } as UserItem

function setup() {
  const reload = vi.fn<() => Promise<void>>().mockResolvedValue()
  const showPassword = vi.fn<(username: string, password: string) => void>()
  const deleted = vi.fn<(userId: string) => void>()
  return { reload, showPassword, deleted, actions: useUserActions({ reload, showPassword, deleted }) }
}

describe('useUserActions', () => {
  beforeEach(() => {
    Object.values(api).forEach(fn => fn.mockReset())
    ui.confirm.mockReset().mockResolvedValue('confirm')
    ui.success.mockReset()
    ui.error.mockReset()
  })

  it('取消确认框时什么都不做', async () => {
    ui.confirm.mockRejectedValue('cancel')
    const { actions, reload } = setup()
    await actions.remove(user)
    await actions.toggleStatus(user)
    await actions.resetPassword(user)
    await actions.revokeSessions(user)
    expect(Object.values(api).every(fn => fn.mock.calls.length === 0)).toBe(true)
    expect(reload).not.toHaveBeenCalled()
  })

  it('启用的账号点开关是停用，并带着版本号提交', async () => {
    api.updateUser.mockResolvedValue({})
    const { actions, reload } = setup()
    await actions.toggleStatus(user)
    expect(api.updateUser).toHaveBeenCalledWith('u1', { status: 'disabled', version: 4 })
    expect(ui.success).toHaveBeenCalledWith('已停用')
    expect(reload).toHaveBeenCalledOnce()
  })

  it('停用的账号点开关是启用', async () => {
    api.updateUser.mockResolvedValue({})
    const { actions } = setup()
    await actions.toggleStatus({ ...user, status: 'disabled' })
    expect(api.updateUser).toHaveBeenCalledWith('u1', { status: 'active', version: 4 })
  })

  it('删除成功后通知详情抽屉并刷新', async () => {
    api.deleteUser.mockResolvedValue({})
    const { actions, deleted, reload } = setup()
    await actions.remove(user)
    expect(deleted).toHaveBeenCalledWith('u1')
    expect(reload).toHaveBeenCalledOnce()
  })

  it('删除失败只提示，不刷新也不通知', async () => {
    api.deleteUser.mockRejectedValue({ status: 403, code: 'FORBIDDEN', message: '不能删除当前账号' })
    const { actions, deleted, reload } = setup()
    await actions.remove(user)
    expect(ui.error).toHaveBeenCalledWith('不能删除当前账号')
    expect(deleted).not.toHaveBeenCalled()
    expect(reload).not.toHaveBeenCalled()
  })

  it('重置密码把临时密码交给一次性弹窗', async () => {
    api.resetUserPassword.mockResolvedValue({ temporary_password: 'Tmp-123' })
    const { actions, showPassword } = setup()
    await actions.resetPassword(user)
    expect(showPassword).toHaveBeenCalledWith('zhangsan', 'Tmp-123')
  })

  it('强制下线提示撤销的会话数，不刷新列表', async () => {
    api.revokeUserSessions.mockResolvedValue({ revoked: 3 })
    const { actions, reload } = setup()
    await actions.revokeSessions(user)
    expect(ui.success).toHaveBeenCalledWith('已撤销 3 个会话')
    expect(reload).not.toHaveBeenCalled()
  })
})
