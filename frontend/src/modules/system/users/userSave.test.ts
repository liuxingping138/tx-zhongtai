import { describe, expect, it } from 'vitest'

import { ApiRequestError } from '@/api/errors'
import { saveFailureText } from './userSave'

describe('用户详情保存失败的说明', () => {
  it('基本信息存上了、角色没存上时说清楚', () => {
    const denied = new ApiRequestError({ status: 403, code: 'AUTH_PERMISSION_DENIED', message: '不能移除最后一个可登录超级管理员', requestId: null })
    expect(saveFailureText(denied, true)).toBe('基本信息已保存，角色没保存：不能移除最后一个可登录超级管理员')
    expect(saveFailureText(denied, false)).toBe('不能移除最后一个可登录超级管理员')
  })
})
