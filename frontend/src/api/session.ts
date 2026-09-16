import axios from 'axios'

import type { TokenPayload } from './types'

const CSRF_COOKIE = 'csrf_token'
const LOCK_NAME = 'tx-zhongtai-refresh'
const CHANNEL_NAME = 'tx-zhongtai-auth'

type ChannelMessage =
  | { type: 'refresh-start' }
  | { type: 'refresh-done'; access_token: string; must_change_password: boolean }
  | { type: 'refresh-fail' }
  | { type: 'logout' }

let accessToken = ''
let csrfToken = ''
let tokenVersion = 0
let inFlight: Promise<TokenPayload> | null = null
const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(CHANNEL_NAME) : null

const listeners = new Set<(token: string) => void>()

channel?.addEventListener('message', (event: MessageEvent<ChannelMessage>) => {
  const payload = event.data
  if (payload.type === 'refresh-done') {
    setAccessToken(payload.access_token)
  }
  if (payload.type === 'logout') {
    setAccessToken('')
  }
})

export function getAccessToken(): string {
  return accessToken
}

export function setAccessToken(token: string): void {
  accessToken = token
  tokenVersion += 1
  listeners.forEach((listener) => listener(token))
}

export function onAccessTokenChange(listener: (token: string) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getCsrfToken(): string {
  return csrfToken
}

export function setCsrfToken(token: string): void {
  csrfToken = token
}

export function readCsrfCookie(): string {
  if (typeof document === 'undefined') {
    return ''
  }
  const parts = document.cookie.split(';')
  for (const part of parts) {
    const [key, ...rest] = part.trim().split('=')
    if (key === CSRF_COOKIE) {
      return decodeURIComponent(rest.join('='))
    }
  }
  return ''
}

export async function ensureCsrfToken(): Promise<string> {
  const fromCookie = readCsrfCookie()
  if (fromCookie) {
    csrfToken = fromCookie
    return fromCookie
  }
  const response = await axios.get('/api/v1/auth/csrf', { withCredentials: true })
  const token = (response.data?.data?.csrf_token as string | undefined) ?? readCsrfCookie()
  csrfToken = token || ''
  return csrfToken
}

export function broadcastLogout(): void {
  channel?.postMessage({ type: 'logout' } satisfies ChannelMessage)
}

async function postRefresh(): Promise<TokenPayload> {
  await ensureCsrfToken()
  const response = await axios.post(
    '/api/v1/auth/refresh',
    {},
    {
      withCredentials: true,
      headers: { 'X-CSRF-Token': csrfToken || readCsrfCookie() },
    },
  )
  const payload = response.data?.data as TokenPayload
  setAccessToken(payload.access_token)
  const cookieCsrf = readCsrfCookie()
  if (cookieCsrf) {
    csrfToken = cookieCsrf
  }
  return payload
}

export async function refreshSession(): Promise<TokenPayload> {
  if (inFlight) {
    return inFlight
  }
  const startedAt = tokenVersion
  inFlight = (async () => {
    const run = async (): Promise<TokenPayload> => {
      if (tokenVersion !== startedAt && accessToken) {
        return {
          access_token: accessToken,
          token_type: 'Bearer',
          expires_in: 0,
          must_change_password: false,
        }
      }
      channel?.postMessage({ type: 'refresh-start' } satisfies ChannelMessage)
      try {
        const payload = await postRefresh()
        channel?.postMessage({
          type: 'refresh-done',
          access_token: payload.access_token,
          must_change_password: payload.must_change_password,
        } satisfies ChannelMessage)
        return payload
      } catch (error) {
        channel?.postMessage({ type: 'refresh-fail' } satisfies ChannelMessage)
        throw error
      }
    }
    if (typeof navigator !== 'undefined' && navigator.locks?.request) {
      return navigator.locks.request(LOCK_NAME, run)
    }
    return run()
  })().finally(() => {
    inFlight = null
  })
  return inFlight
}

export function isAuthPublicPath(url: string | undefined): boolean {
  if (!url) {
    return false
  }
  return (
    url.includes('/auth/login') ||
    url.includes('/auth/refresh') ||
    url.includes('/auth/csrf')
  )
}
