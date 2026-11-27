import type { NetworkDecision } from '@/api/ipWhitelist'

/** 有效期怎么定：常用时长一点就选；不够用就自定义时长（N 小时 / N 天）或指定到期时间；修改时可以保持不变。 */
export type ExpiryChoice = 'keep' | '2h' | '4h' | '1d' | '3d' | '7d' | '30d' | 'duration' | 'datetime'
export type DurationUnit = 'hour' | 'day'

const MINUTE_MS = 60_000
const HOUR_MS = 3_600_000
const DAY_MS = 86_400_000
/** 后端要求到期时间至少在 10 分钟以后。 */
export const MIN_DURATION_MS = 10 * MINUTE_MS

const PRESET_MS: Partial<Record<ExpiryChoice, number>> = {
  '2h': 2 * HOUR_MS,
  '4h': 4 * HOUR_MS,
  '1d': DAY_MS,
  '3d': 3 * DAY_MS,
  '7d': 7 * DAY_MS,
  '30d': 30 * DAY_MS,
}

export const EXPIRY_CHOICES: { value: ExpiryChoice; label: string }[] = [
  { value: '2h', label: '2 小时' },
  { value: '4h', label: '4 小时' },
  { value: '1d', label: '1 天' },
  { value: '3d', label: '3 天' },
  { value: '7d', label: '7 天' },
  { value: '30d', label: '30 天' },
  { value: 'duration', label: '自定义时长' },
  { value: 'datetime', label: '指定到期时间' },
]

export interface ExpiryForm {
  choice: ExpiryChoice
  /** 自定义时长的数量和单位 */
  amount: number | null
  unit: DurationUnit
  /** 指定到期时间（北京时间 YYYY-MM-DD HH:mm:ss） */
  datetime: string
  /** 修改时原来的到期时间（北京时间） */
  current: string
}

/** 后端回的「YYYY-MM-DD HH:mm:ss」是北京时间。 */
export function parseBeijing(text: string): Date | null {
  if (!text) return null
  const date = new Date(`${text.replace(' ', 'T')}+08:00`)
  return Number.isNaN(date.getTime()) ? null : date
}

/** 显示成北京时间「YYYY-MM-DD HH:mm」。 */
export function formatBeijing(date: Date): string {
  const shifted = new Date(date.getTime() + 8 * HOUR_MS)
  return shifted.toISOString().slice(0, 16).replace('T', ' ')
}

/** 按选择算出到期时刻；算不出（没填、格式不对）返回 null。 */
export function expiryDate(form: ExpiryForm, now: Date = new Date()): Date | null {
  const preset = PRESET_MS[form.choice]
  if (preset) return new Date(now.getTime() + preset)
  if (form.choice === 'keep') return parseBeijing(form.current)
  if (form.choice === 'datetime') return parseBeijing(form.datetime)
  if (!form.amount || form.amount <= 0) return null
  return new Date(now.getTime() + form.amount * (form.unit === 'hour' ? HOUR_MS : DAY_MS))
}

/** 保存前检查；返回空串表示没问题。 */
export function expiryError(form: ExpiryForm, maxDays: number, now: Date = new Date()): string {
  const end = expiryDate(form, now)
  if (!end) return form.choice === 'datetime' ? '请选择到期时间' : '请填写时长'
  if (form.choice === 'keep') return end.getTime() > now.getTime() ? '' : '原来的到期时间已过，请重新选择有效期'
  if (end.getTime() - now.getTime() < MIN_DURATION_MS) return '到期时间至少要在 10 分钟以后'
  if (end.getTime() - now.getTime() > maxDays * DAY_MS + 5 * MINUTE_MS) return `一次最多开通 ${maxDays} 天`
  return ''
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

/** 页面顶部那句：管理员自己此刻的 IP 能不能用限定网络的模块、凭什么。 */
export function decisionText(decision: NetworkDecision, modules: string): string {
  switch (decision.via) {
    case 'office':
      return `你当前的 IP ${decision.ip} 属于公司网络，可以直接使用${modules}。`
    case 'whitelist':
      return `你当前的 IP ${decision.ip} 在你的白名单里，到 ${decision.expires_at} 为止可以使用${modules}。`
    case 'disabled':
      return `本环境没有开启网络限制，任何地方都能使用${modules}。`
    default:
      return `你当前的 IP ${decision.ip} 不在公司网络，也没有你的有效白名单，现在打不开${modules}。`
  }
}
