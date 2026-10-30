import type { ManagedUser } from '@/api/system'

/**
 * 用户列表一行上能给哪些操作。后端在每行给 can_manage：不是超级管理员的用户管理员看超级管理员时为 false，
 * 停用、删除、重置密码、强制下线、解锁这些按钮就不给（点了后端也是 403，还会让页面重拉一遍权限）。
 * 旧接口没有这个字段时按能管处理，交给后端拒绝。
 */
export function canManageRow(row: Pick<ManagedUser, 'can_manage'>, canEditUsers: boolean): boolean {
  return canEditUsers && row.can_manage !== false
}

/** 行上第一个按钮的说法：能分配角色又还没角色的写「分配角色」，能改的写「编辑」，其余「查看」。 */
export function openLabel(row: Pick<ManagedUser, 'can_manage' | 'roles'>, can: { edit: boolean; grant: boolean }): string {
  if (row.can_manage === false) return '查看'
  if (can.grant && !(row.roles ?? []).length) return '分配角色'
  return can.edit || can.grant ? '编辑' : '查看'
}

/**
 * 详情抽屉里存好了（基本信息、角色、单独授权），把新值合进列表那一行，不必整页重载。
 * 只覆盖传来的字段：详情接口不带「单独授权数」，存基本信息时不能把列表上的「+单独授权」抹掉。
 */
export function mergeUserRow<T extends { id: string }>(items: T[], changed: Partial<T> & { id: string }): T[] {
  return items.map(item => (item.id === changed.id ? { ...item, ...changed } : item))
}
