import { writeFileSync } from 'node:fs'

import { adminPasswordFile, changedPasswordSuffix } from './adminSession'

/**
 * 隔离库新建的管理员必须先改初始密码。在用例开始前改一次，
 * 并把可用口令写到本地文件，避免多个用例同时改密。
 */
export default async function globalSetup(): Promise<void> {
  const base = (process.env.P6_GATEWAY || 'http://localhost:8090').replace(/\/$/, '')
  const username = process.env.ADMIN_USERNAME || 'p6admin'
  const password = process.env.ADMIN_PASSWORD || ''
  if (!password) return
  const candidates = [password, password + changedPasswordSuffix]
  try {
    for (const current of candidates) {
      const session = await login(base, username, current)
      if (!session) continue
      if (!session.mustChange) {
        writeFileSync(adminPasswordFile, current)
        return
      }
      const next = current + changedPasswordSuffix
      const changed = await changePassword(base, session, current, next)
      if (changed) {
        writeFileSync(adminPasswordFile, next)
        return
      }
    }
  } catch {
    /* 网关没起来时，模拟接口的用例仍可运行。 */
  }
}

interface Session {
  cookie: string
  csrf: string
  access: string
  mustChange: boolean
}

async function login(base: string, username: string, password: string): Promise<Session | null> {
  const csrfResponse = await fetch(`${base}/api/v1/auth/csrf`)
  if (!csrfResponse.ok) return null
  const csrfBody = await csrfResponse.json() as { data?: { csrf_token?: string } }
  const csrf = csrfBody.data?.csrf_token || ''
  const cookie = cookieHeader(csrfResponse)
  const response = await fetch(`${base}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, Cookie: cookie },
    body: JSON.stringify({ username, password }),
  })
  if (!response.ok) return null
  const body = await response.json() as { data?: { access_token?: string; must_change_password?: boolean } }
  return {
    cookie: mergeCookies(cookie, cookieHeader(response)),
    csrf,
    access: body.data?.access_token || '',
    mustChange: Boolean(body.data?.must_change_password),
  }
}

async function changePassword(base: string, session: Session, oldPassword: string, newPassword: string): Promise<boolean> {
  const response = await fetch(`${base}/api/v1/auth/password`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': session.csrf,
      Cookie: session.cookie,
      Authorization: `Bearer ${session.access}`,
    },
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  })
  return response.ok
}

function cookieHeader(response: Response): string {
  const raw = typeof response.headers.getSetCookie === 'function' ? response.headers.getSetCookie() : []
  return raw.map(item => item.split(';')[0]).filter(Boolean).join('; ')
}

function mergeCookies(first: string, second: string): string {
  const jar = new Map<string, string>()
  for (const part of `${first}; ${second}`.split(';')) {
    const text = part.trim()
    if (!text || !text.includes('=')) continue
    const name = text.slice(0, text.indexOf('='))
    jar.set(name, text)
  }
  return [...jar.values()].join('; ')
}
