import { describe, expect, it } from 'vitest'

import { memberSearchParams } from './memberSearch'

describe('添加成员搜人', () => {
  it('按关键词搜，显示名也能搜到', () => {
    expect(memberSearchParams(' 张三 ')).toEqual({ page: 1, page_size: 50, keyword: ['张三'] })
  })

  it('不输入时列出最近的用户', () => {
    expect(memberSearchParams('  ')).toEqual({ page: 1, page_size: 50 })
  })
})
