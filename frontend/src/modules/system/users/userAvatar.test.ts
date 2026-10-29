import { describe, expect, it } from 'vitest'

import { AVATAR_TONES, avatarText, avatarTone } from './userAvatar'

describe('用户头像', () => {
  it('取显示名第一个字，英文转大写；没有显示名用账号', () => {
    expect(avatarText({ display_name: '刘晓婉', username: 'xiaowan.l@telelands.com' })).toBe('刘')
    expect(avatarText({ display_name: 'kevin', username: 'k' })).toBe('K')
    expect(avatarText({ display_name: ' ', username: 'admin' })).toBe('A')
    expect(avatarText({ display_name: '', username: '' })).toBe('?')
  })

  it('同一个人颜色固定，落在色板范围内', () => {
    const id = '2e3880ff-e6af-430b-96c1-21366e24e3df'
    expect(avatarTone(id)).toBe(avatarTone(id))
    const tones = new Set(Array.from({ length: 60 }, (_, i) => avatarTone(`user-${i}`)))
    expect([...tones].every(tone => tone >= 1 && tone <= AVATAR_TONES)).toBe(true)
    expect(tones.size).toBeGreaterThan(3)
  })
})
