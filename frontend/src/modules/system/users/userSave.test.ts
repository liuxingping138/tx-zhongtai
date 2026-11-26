import { describe, expect, it } from 'vitest'

import { ApiRequestError, wasShown } from '@/api/errors'
import { saveFailureText } from './userSave'

describe('用户详情保存失败的说明', () => {
  it('基本信息存上了、角色没存上时说清楚', () => {
    const denied = new ApiRequestError({ status: 403, code: 'AUTH_PERMISSION_DENIED', message: '不能移除最后一个可登录超级管理员', requestId: null })
    expect(saveFailureText(denied, true)).toBe('基本信息已保存，角色没保存：不能移除最后一个可登录超级管理员')
    expect(saveFailureText(denied, false)).toBe('不能移除最后一个可登录超级管理员')
    expect(wasShown(denied)).toBe(true)
  })

  it('版本冲突 409 返回并发提示并标记为已展示，避免请求层重复弹窗', () => {
    const conflict = new ApiRequestError({ status: 409, code: 'VERSION_CONFLICT', message: 'version mismatch', requestId: null })
    expect(saveFailureText(conflict, false)).toBe('该用户刚被其他人修改过，请关闭后重新打开再改。')
    expect(wasShown(conflict)).toBe(true)
  })

  it('重复项 409（DUPLICATE）保留后端原因并标记为已展示', () => {
    const duplicate = new ApiRequestError({ status: 409, code: 'DUPLICATE', message: '邮箱已被占用', requestId: null })
    expect(saveFailureText(duplicate, false)).toBe('邮箱已被占用')
    expect(wasShown(duplicate)).toBe(true)
  })
})
