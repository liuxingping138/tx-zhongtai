import { formatTime } from '@/utils/time'

/** 在线用户、登录日志、用户列表共用的说法：浏览器、多久以前、失败原因、锁定还剩多久。 */

const BROWSERS: [RegExp, string][] = [
  [/Edg\//, 'Edge'],
  [/(MicroMessenger|wxwork)/i, '微信'],
  [/DingTalk/i, '钉钉'],
  [/Firefox\//, 'Firefox'],
  [/Chrome\//, 'Chrome'],
  [/Safari\//, 'Safari'],
]
const SYSTEMS: [RegExp, string][] = [
  [/iPhone|iPad/, 'iOS'],
  [/Android/, 'Android'],
  [/Windows/, 'Windows'],
  [/Mac OS X|Macintosh/, 'macOS'],
  [/Linux/, 'Linux'],
]

/** 「Mozilla/5.0 (Macintosh…) … Chrome/130…」→「Chrome · macOS」；认不出的原样截短。 */
export function browserOf(userAgent: string | null | undefined): string {
  if (!userAgent) return '—'
  const browser = BROWSERS.find(([pattern]) => pattern.test(userAgent))?.[1]
  const system = SYSTEMS.find(([pattern]) => pattern.test(userAgent))?.[1]
  if (!browser && !system) return userAgent.slice(0, 40)
  return [browser, system].filter(Boolean).join(' · ')
}

/** 一小时内说「N 分钟前」，今天说「今天 10:50」，今年更早的「10-28 17:28」，往年才写年份；都只占一行。 */
export function sinceText(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return '—'
  const at = new Date(value)
  if (Number.isNaN(at.getTime())) return formatTime(value)
  const minutes = Math.floor((now.getTime() - at.getTime()) / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const full = formatTime(value)
  const today = formatTime(now.toISOString())
  if (full.slice(0, 10) === today.slice(0, 10)) return `今天 ${full.slice(11, 16)}`
  return full.slice(0, 4) === today.slice(0, 4) ? full.slice(5, 16) : full.slice(0, 16)
}

/** 锁定剩余秒数 →「已锁定，4 分钟后自动解锁」。 */
export function lockText(seconds: number): string {
  const minutes = Math.max(1, Math.ceil(seconds / 60))
  return `已锁定，${minutes} 分钟后自动解锁`
}

const FAILURE_REASONS: Record<string, string> = {
  unauthenticated: '密码错误或账号不存在',
  disabled: '账号已停用',
  // 旧记录：没分账号还是出口 IP。
  locked: '输错次数过多，已锁定',
  locked_account: '这个账号输错次数过多，已锁定',
  locked_ip: '这个网络出口输错次数过多，已暂时限制（同一出口的人都登不上）',
}

/** 登录日志一行的结果：成功、退出，或者失败及原因。 */
export function loginResult(event: { action_code: string | null; outcome: string; error_code: string | null }): {
  tone: 'ok' | 'bad' | 'plain'
  text: string
} {
  if (event.action_code === 'logout') return { tone: 'plain', text: '退出登录' }
  if (event.action_code === 'logout_all') return { tone: 'plain', text: '退出全部设备' }
  if (event.outcome === 'success') return { tone: 'ok', text: '登录成功' }
  return { tone: 'bad', text: `失败：${FAILURE_REASONS[event.error_code ?? ''] ?? '登录失败'}` }
}
