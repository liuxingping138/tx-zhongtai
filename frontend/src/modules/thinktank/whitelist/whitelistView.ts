import type { NetworkDecision } from '@/api/thinktankAccess'

export type ExpiryPreset = '1d' | '3d' | '7d' | '30d' | 'custom'

export const EXPIRY_PRESETS: { value: ExpiryPreset; label: string; days: number }[] = [
  { value: '1d', label: '1 天', days: 1 },
  { value: '3d', label: '3 天', days: 3 },
  { value: '7d', label: '7 天', days: 7 },
  { value: '30d', label: '30 天', days: 30 },
  { value: 'custom', label: '自定义', days: 0 },
]

const DAY_MS = 86_400_000
const HOUR_MS = 3_600_000
const MINUTE_MS = 60_000

/** 从现在起往后 N 天，发给后端的带时区 ISO 时间。 */
export function presetExpiry(preset: ExpiryPreset, now: Date = new Date()): string {
  const days = EXPIRY_PRESETS.find(item => item.value === preset)?.days ?? 0
  return new Date(now.getTime() + days * DAY_MS).toISOString()
}

/** 后端回的「YYYY-MM-DD HH:mm:ss」是北京时间。 */
export function parseBeijing(text: string): Date | null {
  if (!text) return null
  const date = new Date(`${text.replace(' ', 'T')}+08:00`)
  return Number.isNaN(date.getTime()) ? null : date
}

export function remainingText(expiresAt: string, now: Date = new Date()): string {
  const end = parseBeijing(expiresAt)
  if (!end) return ''
  const left = end.getTime() - now.getTime()
  if (left <= 0) return '已过期'
  if (left >= DAY_MS) return `还剩 ${Math.floor(left / DAY_MS)} 天`
  if (left >= HOUR_MS) return `还剩 ${Math.floor(left / HOUR_MS)} 小时`
  return `还剩 ${Math.max(1, Math.floor(left / MINUTE_MS))} 分钟`
}

/** 页面顶部那句：管理员自己此刻的 IP 能不能用智库、凭什么。 */
export function decisionText(decision: NetworkDecision): string {
  switch (decision.via) {
    case 'office':
      return `你当前的 IP ${decision.ip} 属于公司网络，可以直接使用智库。`
    case 'whitelist':
      return `你当前的 IP ${decision.ip} 在白名单里，到 ${decision.expires_at} 为止可以使用智库。`
    case 'disabled':
      return '本环境没有开启网络限制，任何地方都能使用智库。'
    default:
      return `你当前的 IP ${decision.ip} 不在公司网络，也没有有效白名单，现在打不开资料库等页面。`
  }
}
