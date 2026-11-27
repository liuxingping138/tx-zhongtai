import { describe, expect, it } from 'vitest'

import { networkDeniedMessage, noteNetworkDenied } from './networkDenied'

describe('智库网络准入的 403', () => {
  it('认出网络准入并记下带 IP 的说明', () => {
    const message = '智库只能在公司网络下访问。你当前的 IP 是 5.6.7.8'
    expect(noteNetworkDenied({ status: 403, code: 'THINKTANK_NETWORK_DENIED', message, requestId: null })).toBe(true)
    expect(networkDeniedMessage.value).toBe(message)
  })

  it('普通的没有权限不算', () => {
    networkDeniedMessage.value = ''
    expect(noteNetworkDenied({ status: 403, code: 'AUTH_PERMISSION_DENIED', message: '没有权限', requestId: null })).toBe(false)
    expect(noteNetworkDenied(undefined)).toBe(false)
    expect(networkDeniedMessage.value).toBe('')
  })
})
