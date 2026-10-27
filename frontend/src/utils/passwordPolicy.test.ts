import { describe, expect, it } from 'vitest'

import { passwordError } from './passwordPolicy'

describe('密码规则', () => {
  it('和后端一致：至少 8 位，同时有字母和数字', () => {
    expect(passwordError('short1')).toBe('新密码至少 8 位')
    expect(passwordError('11111111')).toBe('新密码要同时包含字母和数字')
    expect(passwordError('longenough')).toBe('新密码要同时包含字母和数字')
    expect(passwordError('long-enough1')).toBe('')
  })
})
