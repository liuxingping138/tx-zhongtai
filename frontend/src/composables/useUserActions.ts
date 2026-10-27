import { ElMessage, ElMessageBox } from 'element-plus'

import { errorMessage } from '@/api/errors'
import { deleteUser, resetUserPassword, revokeUserSessions, updateUser } from '@/api/system'
import type { UserItem } from '@/api/types'

interface UserActionsOptions {
  /** 操作成功后刷新列表。 */
  reload: () => Promise<void>
  /** 重置密码得到的临时密码，只显示这一次。 */
  showPassword: (username: string, password: string) => void
  /** 用户被删除后，如果正开着他的详情，要关掉。 */
  deleted: (userId: string) => void
}

async function confirm(message: string, title: string, options: Record<string, unknown> = {}): Promise<boolean> {
  return ElMessageBox.confirm(message, title, { type: 'warning', ...options }).then(() => true, () => false)
}

/** 用户列表行上的危险操作：每个都先确认，成功后提示并刷新，失败只提示不刷新。 */
export function useUserActions(options: UserActionsOptions) {
  async function toggleStatus(user: UserItem): Promise<void> {
    const next = user.status === 'active' ? 'disabled' : 'active'
    const label = next === 'disabled' ? '停用' : '启用'
    if (!await confirm(`确认${label}用户 ${user.username} ？`, '请确认')) return
    try {
      await updateUser(user.id, { status: next, version: user.version })
      ElMessage.success(`已${label}`)
      await options.reload()
    } catch (error) {
      ElMessage.error(errorMessage(error, `${label}失败`))
    }
  }

  async function remove(user: UserItem): Promise<void> {
    const sure = await confirm(
      `删除后，${user.username} 不能再登录，也不会出现在用户列表里。操作日志仍保留。这个用户名以后可以重新使用。`,
      '删除用户',
      { confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' },
    )
    if (!sure) return
    try {
      await deleteUser(user.id)
      ElMessage.success('已删除')
      options.deleted(user.id)
      await options.reload()
    } catch (error) {
      ElMessage.error(errorMessage(error, '删除失败'))
    }
  }

  async function resetPassword(user: UserItem): Promise<void> {
    if (!await confirm(`将重置 ${user.username} 的密码并强制其下次登录改密，是否继续？`, '重置密码')) return
    try {
      const result = await resetUserPassword(user.id)
      options.showPassword(user.username, result.temporary_password)
      ElMessage.success('已重置密码')
      await options.reload()
    } catch (error) {
      ElMessage.error(errorMessage(error, '重置失败'))
    }
  }

  async function revokeSessions(user: UserItem): Promise<void> {
    if (!await confirm(`确认强制下线 ${user.username} 的全部会话？`, '强制下线')) return
    try {
      const result = await revokeUserSessions(user.id)
      ElMessage.success(`已撤销 ${result.revoked} 个会话`)
    } catch (error) {
      ElMessage.error(errorMessage(error, '下线失败'))
    }
  }

  return { toggleStatus, remove, resetPassword, revokeSessions }
}
