import type { OnlineDevice } from '@/api/system'

/**
 * 在线用户页的两个说法：
 * - 有效登录：登录后没退出、没过期的设备（刷新令牌 7 天内都有效），可能早就没在用了；
 * - 在线：其中最近 30 分钟内有过操作的。
 */
export type SessionView = 'online' | 'all'

export interface SessionCounts {
  onlinePeople: number
  onlineDevices: number
  validPeople: number
  validDevices: number
}

function people(items: OnlineDevice[]): number {
  return new Set(items.map(item => item.user.id)).size
}

export function sessionCounts(items: OnlineDevice[]): SessionCounts {
  const online = items.filter(item => item.online)
  return {
    onlinePeople: people(online),
    onlineDevices: online.length,
    validPeople: people(items),
    validDevices: items.length,
  }
}

export function visibleSessions(items: OnlineDevice[], view: SessionView): OnlineDevice[] {
  return view === 'online' ? items.filter(item => item.online) : items
}

/** 「30 分钟」：窗口按接口给的秒数写，不在页面里写死。 */
export function windowText(seconds: number | null | undefined): string {
  const minutes = Math.max(1, Math.round((seconds || 1800) / 60))
  return minutes % 60 === 0 ? `${minutes / 60} 小时` : `${minutes} 分钟`
}

/** 操作列：正在用的这台写「当前设备」不给下线；管不了的（超级管理员的设备）不给按钮。 */
export function deviceAction(item: Pick<OnlineDevice, 'current' | 'can_manage'>, canRevoke: boolean): 'current' | 'revoke' | 'none' {
  if (item.current) return 'current'
  return canRevoke && item.can_manage ? 'revoke' : 'none'
}
