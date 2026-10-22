import { describe, expect, it } from 'vitest'

import { ALL_CATEGORIES, defaultCategory, inCategory } from './categories'

const policy = { code: 'policy', name: '政策', editable: true }
const tender = { code: 'tender', name: '招投标', editable: true }

describe('模板类型', () => {
  it('「全部」不过滤，选了类型只留这一类', () => {
    expect(inCategory('policy', ALL_CATEGORIES)).toBe(true)
    expect([inCategory('policy', 'tender'), inCategory('tender', 'tender')]).toEqual([false, true])
  })

  it('新模板默认用正在看的类型，看的是只读类型或「全部」时用第一个能编辑的', () => {
    expect(defaultCategory([policy, tender], 'tender')).toBe('tender')
    expect(defaultCategory([policy, tender], 'customer')).toBe('policy')
    expect(defaultCategory([policy], ALL_CATEGORIES)).toBe('policy')
    expect(defaultCategory([], ALL_CATEGORIES)).toBe('')
  })
})
