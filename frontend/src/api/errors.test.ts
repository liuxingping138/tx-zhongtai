import { describe, expect, it } from 'vitest'

import { ApiRequestError, errorMessage } from './errors'

describe('errorMessage', () => {
  it('接口错误和普通错误都优先用自带的说明', () => {
    const apiError = new ApiRequestError({ status: 409, code: 'CONFLICT', message: '数据已被他人修改', requestId: null })
    expect(errorMessage(apiError, '保存失败')).toBe('数据已被他人修改')
    expect(errorMessage(new Error('网络断开'), '保存失败')).toBe('网络断开')
  })

  it('说明为空或不是错误对象时用兜底提示，不显示空白', () => {
    expect(errorMessage(new Error(''), '保存失败')).toBe('保存失败')
    expect(errorMessage({ status: 500, code: 'X', message: '', requestId: null }, '保存失败')).toBe('保存失败')
    expect(errorMessage('oops', '保存失败')).toBe('保存失败')
  })
})
